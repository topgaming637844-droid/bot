from datetime import datetime, timedelta, timezone
from typing import Optional
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.exceptions import TelegramBadRequest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aiogram.filters import StateFilter
from app.database.models import SearchCache, UserFavorites, EpisodeCache
from app.services.anilist import search_anilist
from app.services.scraper import search_anime_scraper, get_episodes_scraper, ScraperError
from app.utils.logging_config import logger

router = Router(name="search")

class SearchStates(StatesGroup):
    waiting_for_episode = State()

CACHE_EXPIRATION_HOURS = 24

@router.message(F.text & ~F.text.startswith("/"), StateFilter(None))
async def handle_anime_search(message: Message, db_session: AsyncSession, state: FSMContext):
    """
    Handles search queries. Queries database cache first,
    then normalizes using AniList GraphQL API and displays matches.
    If AniList fails, falls back to WitAnime.
    """
    query = message.text.strip().lower()
    if not query:
        return

    logger.info(f"بدء البحث عن أنمي: '{query}' (معرف المستخدم: {message.from_user.id})")

    # Check search cache first
    stmt = select(SearchCache).where(SearchCache.query_text == query)
    res = await db_session.execute(stmt)
    cached_entries = res.scalars().all()

    resolved_anime = []

    # If cached and not expired (24h)
    if cached_entries and (datetime.now(timezone.utc) - cached_entries[0].created_at) < timedelta(hours=CACHE_EXPIRATION_HOURS):
        logger.info(f"وجد كاش للبحث: '{query}' يحتوي على {len(cached_entries)} نتائج.")
        for entry in cached_entries:
            resolved_anime.append({
                "anilist_id": entry.anilist_id,
                "title_english": entry.title_english,
                "title_romaji": entry.title_romaji,
                "description": entry.description,
                "image_url": entry.image_url
            })
    else:
        logger.info(f"كاش غير متوفر للبحث: '{query}'. جاري الاستعلام من قواعد البيانات...")
        status_msg = await message.answer("🔍 جاري فحص الفهرس السحابي.. anime")
        try:
            anilist_results = await search_anilist(query)
            await message.bot.delete_message(chat_id=message.chat.id, message_id=status_msg.message_id)
            
            if not anilist_results:
                logger.info(f"الخدمة الرئيسية لم ترجع نتائج للبحث: '{query}'. جاري الانتقال للبحث المساعد...")
                status_msg = await message.answer("🔍 جاري توسيع نطاق البحث في قواعد البيانات...")
                scraper_results = await search_anime_scraper(query)
                await message.bot.delete_message(chat_id=message.chat.id, message_id=status_msg.message_id)
                
                if not scraper_results:
                    logger.info(f"لم ترجع نتائج للبحث: '{query}'")
                    await message.answer("⚠️ عذراً، خادم البث يواجه ضغطاً حالياً، يرجى المحاولة لاحقاً.")
                    return
                
                for r in scraper_results:
                    # Generate a unique negative ID for database indexing
                    witanime_id = -abs(hash(r["slug"]) % 100000000)
                    resolved_anime.append({
                        "anilist_id": witanime_id,
                        "title_english": r["title"],
                        "title_romaji": f"WITANIME:{r['slug']}",
                        "description": "نتائج بحث مستخرجة مباشرة من سيرفر WitAnime المساعد.",
                        "image_url": None
                    })
            else:
                resolved_anime = anilist_results
            
            # Clear old cache for this query first
            stmt_del = select(SearchCache).where(SearchCache.query_text == query)
            res_del = await db_session.execute(stmt_del)
            old_entries = res_del.scalars().all()
            for old_entry in old_entries:
                await db_session.delete(old_entry)
            await db_session.commit()
            
            # Cache all resolved results (up to 10)
            logger.info(f"كاش جديد للبحث '{query}' يحتوي على {len(resolved_anime)} نتائج.")
            for anime in resolved_anime[:10]:
                new_cache = SearchCache(
                    query_text=query,
                    anilist_id=anime["anilist_id"],
                    title_english=anime["title_english"],
                    title_romaji=anime["title_romaji"],
                    description=anime["description"],
                    image_url=anime["image_url"],
                    duration=anime.get("duration")[:90] if anime.get("duration") else None,
                    synonyms=anime.get("synonyms")
                )
                db_session.add(new_cache)
            await db_session.commit()
            
        except Exception as e:
            logger.exception("خطأ أثناء معالجة البحث وتطبيع الاستعلام")
            try:
                if 'status_msg' in locals():
                    await message.bot.delete_message(chat_id=message.chat.id, message_id=status_msg.message_id)
            except Exception:
                pass
            import html
            await message.answer(f"❌ حدث خطأ أثناء البحث: {html.escape(str(e))}")
            return

    # Build selection keyboard
    keyboard_buttons = []
    for anime in resolved_anime[:5]:
        title = anime["title_english"] or anime["title_romaji"]
        if title.startswith("WITANIME:"):
            title = anime["title_english"]  # clean name
        keyboard_buttons.append([
            InlineKeyboardButton(
                text=title[:40] + "..." if len(title) > 43 else title,
                callback_data=f"sel_anime:{anime['anilist_id']}"
            )
        ])
        
    if len(resolved_anime) > 5:
        keyboard_buttons.append([
            InlineKeyboardButton(text="📄 إظهار المزيد من النتائج", callback_data=f"more_results:{query}")
        ])

    markup = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    await message.answer(
        "✨ **نتائج البحث**:\nاختر الأنمي لعرض خيارات الحلقات والتحميل:",
        reply_markup=markup,
        parse_mode="Markdown"
    )

@router.callback_query(F.data.startswith("sel_anime:"))
async def handle_anime_selection(callback: CallbackQuery, db_session: AsyncSession, state: FSMContext):
    """
    Handles anime selection from the keyboard.
    Loads and caches episodes, calculates ranges, and prompts the user in Arabic.
    """
    anilist_id = int(callback.data.split(":")[1])
    logger.info(f"اختيار أنمي (معرف أنيليست: {anilist_id}، معرف المستخدم: {callback.from_user.id})")
    
    # Retrieve details from search_cache
    stmt = select(SearchCache).where(SearchCache.anilist_id == anilist_id)
    res = await db_session.execute(stmt)
    cache_entry = res.scalars().first()
    
    if not cache_entry:
        logger.warning(f"لم يتم العثور على كاش للأنمي: {anilist_id}")
        await callback.answer("❌ تفاصيل الأنمي غير موجودة في الكاش. يرجى البحث مجدداً.", show_alert=True)
        return
        
    title = cache_entry.title_english or cache_entry.title_romaji
    if title.startswith("WITANIME:"):
        title = cache_entry.title_english

    # Instead of deleting and answering, we edit callback.message in-place to loading state
    try:
        await callback.message.edit_text("🔍 جاري جلب قائمة الحلقات...")
    except TelegramBadRequest:
        try:
            await callback.message.edit_caption(caption="🔍 جاري جلب قائمة الحلقات...")
        except Exception:
            pass
    
    try:
        anime_slug = None
        if cache_entry.title_romaji.startswith("WITANIME:"):
            anime_slug = cache_entry.title_romaji.split(":", 1)[1]
        else:
            # Check if already cached and not expired
            stmt_eps = select(EpisodeCache).where(EpisodeCache.anilist_id == anilist_id)
            res_eps = await db_session.execute(stmt_eps)
            cached_episodes = res_eps.scalars().all()
            
            if cached_episodes and (datetime.now(timezone.utc) - cached_episodes[0].created_at) < timedelta(hours=CACHE_EXPIRATION_HOURS):
                # Hit cache
                pass
            else:
                # Need to search slug on scraper
                from app.utils.match import get_best_slug_match, sanitize_search_query
                search_title = cache_entry.title_romaji or cache_entry.title_english
                cleaned_title = sanitize_search_query(search_title)
                
                matched_query = cleaned_title
                scraper_results = await search_anime_scraper(cleaned_title)
                
                if not scraper_results and cache_entry.title_english:
                    cleaned_eng = sanitize_search_query(cache_entry.title_english)
                    if cleaned_eng != cleaned_title:
                        matched_query = cleaned_eng
                        scraper_results = await search_anime_scraper(cleaned_eng)

                # Fallback to synonyms from AniList if primary titles returned 0 results
                if not scraper_results and cache_entry.synonyms:
                    for syn in cache_entry.synonyms:
                        cleaned_syn = sanitize_search_query(syn)
                        if cleaned_syn and cleaned_syn != cleaned_title:
                            logger.info(f"محاولة البحث بالمرادف المصاحب (Synonym): '{cleaned_syn}'")
                            scraper_results = await search_anime_scraper(cleaned_syn)
                            if scraper_results:
                                matched_query = cleaned_syn
                                break
                        
                if not scraper_results:
                    try:
                        await callback.message.edit_text("❌ لم يتم العثور على هذا الأنمي في خوادم البث المساعدة.")
                    except TelegramBadRequest:
                        try:
                            await callback.message.edit_caption(caption="❌ لم يتم العثور على هذا الأنمي في خوادم البث المساعدة.")
                        except Exception:
                            pass
                    return
                    
                anime_slug = get_best_slug_match(scraper_results, matched_query)

        scraped_data = None
        if anime_slug:
            # Scrape and cache episodes
            scraped_data = await get_episodes_scraper(anime_slug)
            if not scraped_data or not scraped_data.get("episodes"):
                try:
                    await callback.message.edit_text("❌ فشل في جلب قائمة الحلقات من سيرفر البث المساعد.")
                except TelegramBadRequest:
                    try:
                        await callback.message.edit_caption(caption="❌ فشل في جلب قائمة الحلقات من سيرفر البث المساعد.")
                    except Exception:
                        pass
                return
                
            episodes_list = scraped_data["episodes"]
            
            # If database cache lacks high-res details, update them
            updated = False
            if scraped_data.get("poster_url") and (not cache_entry.image_url or "default" in cache_entry.image_url):
                cache_entry.image_url = scraped_data["poster_url"]
                updated = True
            if scraped_data.get("description") and scraped_data["description"] != "لا يوجد":
                cache_entry.description = scraped_data["description"]
                updated = True
            if scraped_data.get("duration"):
                cache_entry.duration = scraped_data["duration"]
                updated = True
            if updated:
                db_session.add(cache_entry)
                await db_session.commit()
                
            # Delete old cache
            stmt_del = select(EpisodeCache).where(EpisodeCache.anilist_id == anilist_id)
            res_del = await db_session.execute(stmt_del)
            old_eps = res_del.scalars().all()
            for old_ep in old_eps:
                await db_session.delete(old_ep)
                
            # Add new episodes to cache
            for ep in episodes_list:
                db_ep = EpisodeCache(
                    anilist_id=anilist_id,
                    ep_number=ep["ep_number"],
                    play_url=ep["play_url"]
                )
                db_session.add(db_ep)
            await db_session.commit()
    except ScraperError as se:
        logger.warning(f"Scraper error for anilist_id={anilist_id}: {se}")
        msg = "❌ فشل جلب الحلقات من خادم البث المساعد."
        if "CLOUDFLARE_BLOCK" in str(se):
            msg = "⚠️ عذراً، خادم البث المساعد محمي بحماية Cloudflare حالياً وتتحقق منها خوارزميات المنع. يرجى مراجعة إعدادات البروكسي أو المحاولة لاحقاً."
        try:
            await callback.message.edit_text(msg)
        except TelegramBadRequest:
            try:
                await callback.message.edit_caption(caption=msg)
            except Exception:
                pass
        return
    except Exception as e:
        logger.exception(f"Unexpected error fetching episodes for anilist_id={anilist_id}")
        msg = "❌ حدث خطأ غير متوقع أثناء جلب الحلقات. يرجى المحاولة لاحقاً."
        try:
            await callback.message.edit_text(msg)
        except TelegramBadRequest:
            try:
                await callback.message.edit_caption(caption=msg)
            except Exception:
                pass
        return

    # Load final episode list from DB
    stmt_eps = select(EpisodeCache).where(EpisodeCache.anilist_id == anilist_id)
    res_eps = await db_session.execute(stmt_eps)
    cached_episodes = res_eps.scalars().all()

    if not cached_episodes:
        try:
            await callback.message.edit_text("❌ فشل في تحميل الحلقات من قاعدة البيانات.")
        except TelegramBadRequest:
            try:
                await callback.message.edit_caption(caption="❌ فشل في تحميل الحلقات من قاعدة البيانات.")
            except Exception:
                pass
        return
    
    # Store details in FSM context
    await state.update_data(
        anilist_id=anilist_id,
        anime_title=title,
        title_romaji=cache_entry.title_romaji,
        title_english=cache_entry.title_english,
        duration=cache_entry.duration or (scraped_data.get("duration") if scraped_data else None)
    )
    
    await callback.answer()

    await render_episode_keyboard(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
        anilist_id=anilist_id,
        db_session=db_session
    )


def parse_ep_num(ep_str: str) -> float:
    if not ep_str:
        return 0.0
    try:
        return float(str(ep_str).strip())
    except (ValueError, TypeError):
        import re
        match = re.search(r'(\d+(?:\.\d+)?)', str(ep_str))
        if match:
            try:
                return float(match.group(1))
            except Exception:
                pass
        return 999999.0


async def render_episode_keyboard(
    bot,
    chat_id,
    message_id: Optional[int],
    anilist_id: int,
    db_session: AsyncSession,
    start_ep: Optional[int] = None,
    end_ep: Optional[int] = None
):
    stmt = select(SearchCache).where(SearchCache.anilist_id == anilist_id)
    res = await db_session.execute(stmt)
    cache_entry = res.scalars().first()
    if not cache_entry:
        return
        
    title = cache_entry.title_english or cache_entry.title_romaji
    if title.startswith("WITANIME:"):
        title = cache_entry.title_english
        
    # Get all episodes from the cache
    stmt_eps = select(EpisodeCache).where(EpisodeCache.anilist_id == anilist_id)
    res_eps = await db_session.execute(stmt_eps)
    cached_episodes = list(res_eps.scalars().all())
    
    # Sort them using float parse_ep_num safely
    try:
        cached_episodes.sort(key=lambda ep: parse_ep_num(ep.ep_number))
    except Exception as e:
        logger.warning(f"Error sorting episodes list: {e}")
    
    inline_keyboard = []
    
    import os
    from aiogram.types import WebAppInfo
    from config import config
    webapp_domain = config.WEBAPP_BASE_URL or os.getenv("RAILWAY_PUBLIC_DOMAIN", "")
    if webapp_domain and not webapp_domain.startswith("http"):
        webapp_domain = f"https://{webapp_domain}"
        
    if webapp_domain:
        ep_webapp_url = f"{webapp_domain}/webapp/episodes?anilist_id={anilist_id}"
        inline_keyboard.append([
            InlineKeyboardButton(text="🎬 ابدأ المشاهدة الآن 🍿", web_app=WebAppInfo(url=ep_webapp_url))
        ])

    total_eps = len(cached_episodes)
    
    import html
    poster_prefix = f'<a href="{cache_entry.image_url}">&#8203;</a>' if cache_entry.image_url else ""
    safe_title = html.escape(title)
    safe_desc = html.escape(cache_entry.description[:250] + '...') if cache_entry.description else 'لا يوجد'

    text = (
        f"{poster_prefix}🎬 <b>الأنمي المختار:</b> {safe_title}\n"
        f"📖 <b>القصة:</b> {safe_desc}\n\n"
        f"📊 <b>عدد الحلقات المتوفرة:</b> {total_eps} حلقة\n\n"
        f"اضغط على الزر أدناه لفتح واجهة المشاهدة واختيار الحلقة بالجودة المناسبة:"
    )
            
    # Bottom actions: Pristine & Clean
    inline_keyboard.append([
        InlineKeyboardButton(text="⭐ إضافة للمفضلة", callback_data=f"fav_add:{anilist_id}"),
        InlineKeyboardButton(text="🔙 رجوع للبحث", callback_data=f"back_to_search:{anilist_id}")
    ])
    
    markup = InlineKeyboardMarkup(inline_keyboard=inline_keyboard)
    
    if message_id:
        try:
            # Try editing text message directly with HTML zero-width space poster preview
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                reply_markup=markup,
                parse_mode="HTML"
            )
        except TelegramBadRequest:
            try:
                await bot.edit_message_caption(
                    chat_id=chat_id,
                    message_id=message_id,
                    caption=text,
                    reply_markup=markup,
                    parse_mode="HTML"
                )
            except Exception:
                await bot.send_message(chat_id=chat_id, text=text, reply_markup=markup, parse_mode="HTML")
        except Exception:
            await bot.send_message(chat_id=chat_id, text=text, reply_markup=markup, parse_mode="HTML")
    else:
        await bot.send_message(chat_id=chat_id, text=text, reply_markup=markup, parse_mode="HTML")


@router.callback_query(F.data.startswith("ep_block:"))
async def handle_ep_block(callback: CallbackQuery, db_session: AsyncSession):
    parts = callback.data.split(":")
    anilist_id = int(parts[1])
    start = int(parts[2])
    end = int(parts[3])
    await callback.answer()
    await render_episode_keyboard(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
        anilist_id=anilist_id,
        db_session=db_session,
        start_ep=start,
        end_ep=end
    )


@router.callback_query(F.data.startswith("ep_blocks_home:"))
async def handle_ep_blocks_home(callback: CallbackQuery, db_session: AsyncSession):
    parts = callback.data.split(":")
    anilist_id = int(parts[1])
    await callback.answer()
    await render_episode_keyboard(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
        anilist_id=anilist_id,
        db_session=db_session,
        start_ep=None
    )


@router.callback_query(F.data.startswith("sel_ep_click:"))
async def handle_sel_ep_click(callback: CallbackQuery, db_session: AsyncSession):
    parts = callback.data.split(":")
    anilist_id = int(parts[1])
    ep_num = parts[2]
    
    await callback.answer()
    
    from app.handlers.download import prompt_quality_selection
    
    stmt = select(EpisodeCache).where(
        (EpisodeCache.anilist_id == anilist_id) & (EpisodeCache.ep_number == ep_num)
    )
    res = await db_session.execute(stmt)
    ep_entry = res.scalar_one_or_none()
    if not ep_entry:
        try:
            await callback.message.edit_text("❌ انتهت صلاحية الجلسة. يرجى اختيار الحلقة مجدداً.")
        except TelegramBadRequest:
            await callback.message.answer("❌ انتهت صلاحية الجلسة. يرجى اختيار الحلقة مجدداً.")
        return
        
    stmt_s = select(SearchCache).where(SearchCache.anilist_id == anilist_id)
    res_s = await db_session.execute(stmt_s)
    cache_entry = res_s.scalars().first()
    title = cache_entry.title_english or cache_entry.title_romaji if cache_entry else "أنمي"
    if title.startswith("WITANIME:"):
        title = cache_entry.title_english
        
    duration = cache_entry.duration if cache_entry else None
    
    await prompt_quality_selection(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        anilist_id=anilist_id,
        ep_number=ep_num,
        play_url=ep_entry.play_url,
        anime_title=title,
        duration=duration,
        db_session=db_session,
        message_id=callback.message.message_id
    )

@router.callback_query(F.data.startswith("fav_add:"))
async def handle_add_favorite(callback: CallbackQuery, db_session: AsyncSession):
    """
    Saves the anime to UserFavorites table in the database and provides confirmation.
    """
    anilist_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    logger.info(f"إضافة إلى المفضلة (معرف أنيليست: {anilist_id}، معرف المستخدم: {user_id})")

    # Retrieve title from search cache
    stmt = select(SearchCache).where(SearchCache.anilist_id == anilist_id)
    res = await db_session.execute(stmt)
    cache_entry = res.scalars().first()

    if not cache_entry:
        logger.warning(f"تفاصيل الأنمي غير موجودة لإضافتها للمفضلة: {anilist_id}")
        await callback.answer("❌ تفاصيل الأنمي غير متوفرة في الكاش. يرجى البحث مجدداً.", show_alert=True)
        return

    title = cache_entry.title_english or cache_entry.title_romaji
    if title.startswith("WITANIME:"):
        title = cache_entry.title_english

    # Check if already in favorites
    fav_stmt = select(UserFavorites).where(
        (UserFavorites.user_id == user_id) & (UserFavorites.anilist_id == anilist_id)
    )
    fav_res = await db_session.execute(fav_stmt)
    existing_fav = fav_res.scalar_one_or_none()

    if existing_fav:
        logger.info(f"الأنمي '{title}' موجود بالفعل في المفضلة للمستخدم: {user_id}")
        await callback.answer(f"⭐ '{title}' موجود بالفعل في مفضلتك!", show_alert=False)
        return

    # Add to favorites
    try:
        new_fav = UserFavorites(
            user_id=user_id,
            anilist_id=anilist_id,
            anime_title=title
        )
        db_session.add(new_fav)
        await db_session.commit()
        
        logger.info(f"تمت إضافة '{title}' للمفضلة بنجاح للمستخدم: {user_id}")
        await callback.answer(f"✅ تم إضافة '{title}' إلى المفضلة!", show_alert=False)
    except Exception as e:
        logger.exception("خطأ أثناء إضافة المفضلة")
        await db_session.rollback()
        import html
        await callback.answer(f"❌ فشل الحفظ: {html.escape(str(e))}", show_alert=True)


@router.callback_query(F.data.startswith("more_results:"))
async def handle_more_results(callback: CallbackQuery, db_session: AsyncSession):
    """Expards the search results keyboard to show all cached results (up to 10)."""
    await callback.answer()
    query = callback.data.split(":", 1)[1]
    
    # Retrieve all cached results from DB
    stmt = select(SearchCache).where(SearchCache.query_text == query)
    res = await db_session.execute(stmt)
    cached_entries = res.scalars().all()
    
    if not cached_entries:
        try:
            await callback.message.edit_text("❌ انتهت صلاحية البحث. يرجى كتابة اسم الأنمي مجدداً للبحث.")
        except TelegramBadRequest:
            await callback.message.answer("❌ انتهت صلاحية البحث. يرجى كتابة اسم الأنمي مجدداً للبحث.")
        return
        
    keyboard_buttons = []
    for entry in cached_entries[:10]:
        title = entry.title_english or entry.title_romaji
        if title.startswith("WITANIME:"):
            title = entry.title_english
        keyboard_buttons.append([
            InlineKeyboardButton(
                text=title[:40] + "..." if len(title) > 43 else title,
                callback_data=f"sel_anime:{entry.anilist_id}"
            )
        ])
        
    markup = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    try:
        await callback.message.edit_text(
            "✨ **نتائج البحث**:\nاختر الأنمي لعرض خيارات الحلقات والتحميل:",
            reply_markup=markup,
            parse_mode="Markdown"
        )
    except TelegramBadRequest:
        try:
            await callback.bot.edit_message_reply_markup(
                chat_id=callback.message.chat.id,
                message_id=callback.message.message_id,
                reply_markup=markup
            )
        except Exception:
            pass


@router.callback_query(F.data.startswith("back_to_search:"))
async def handle_back_to_search(callback: CallbackQuery, db_session: AsyncSession):
    anilist_id = int(callback.data.split(":")[1])
    await callback.answer()
    
    # 1. Get search query from cache
    stmt = select(SearchCache).where(SearchCache.anilist_id == anilist_id)
    res = await db_session.execute(stmt)
    cache_entry = res.scalars().first()
    if not cache_entry:
        try:
            await callback.message.edit_text("❌ انتهت صلاحية البحث. يرجى كتابة اسم الأنمي مجدداً للبحث.")
        except TelegramBadRequest:
            await callback.message.answer("❌ انتهت صلاحية البحث. يرجى كتابة اسم الأنمي مجدداً للبحث.")
        return
        
    query = cache_entry.query_text
    
    # 2. Retrieve all cached entries for this query
    stmt_all = select(SearchCache).where(SearchCache.query_text == query)
    res_all = await db_session.execute(stmt_all)
    cached_entries = res_all.scalars().all()
    
    if not cached_entries:
        try:
            await callback.message.edit_text("❌ انتهت صلاحية البحث. يرجى كتابة اسم الأنمي مجدداً للبحث.")
        except TelegramBadRequest:
            await callback.message.answer("❌ انتهت صلاحية البحث. يرجى كتابة اسم الأنمي مجدداً للبحث.")
        return
        
    # 3. Build search results keyboard
    keyboard_buttons = []
    for entry in cached_entries[:5]:
        title = entry.title_english or entry.title_romaji
        if title.startswith("WITANIME:"):
            title = entry.title_english
        keyboard_buttons.append([
            InlineKeyboardButton(
                text=title[:40] + "..." if len(title) > 43 else title,
                callback_data=f"sel_anime:{entry.anilist_id}"
            )
        ])
        
    if len(cached_entries) > 5:
        keyboard_buttons.append([
            InlineKeyboardButton(text="📄 إظهار المزيد من النتائج", callback_data=f"more_results:{query}")
        ])
        
    markup = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    
    # Edit in-place with cascading fallback
    try:
        try:
            await callback.bot.edit_message_caption(
                chat_id=callback.message.chat.id,
                message_id=callback.message.message_id,
                caption="✨ **نتائج البحث**:\nاختر الأنمي لعرض خيارات الحلقات والتحميل:",
                reply_markup=markup,
                parse_mode="Markdown"
            )
        except TelegramBadRequest as e:
            if "there is no caption in the message" in str(e).lower() or "message is not modified" in str(e).lower():
                await callback.bot.edit_message_text(
                    chat_id=callback.message.chat.id,
                    message_id=callback.message.message_id,
                    text="✨ **نتائج البحث**:\nاختر الأنمي لعرض خيارات الحلقات والتحميل:",
                    reply_markup=markup,
                    parse_mode="Markdown"
                )
            else:
                raise
    except Exception:
        # Final fallback: send a new message
        await callback.message.answer(
            "✨ **نتائج البحث**:\nاختر الأنمي لعرض خيارات الحلقات والتحميل:",
            reply_markup=markup,
            parse_mode="Markdown"
        )

