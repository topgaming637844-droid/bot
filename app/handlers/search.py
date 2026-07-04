from datetime import datetime, timedelta, timezone
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aiogram.filters import StateFilter
from app.database.models import SearchCache, UserFavorites, EpisodeCache
from app.services.anilist import search_anilist
from app.services.scraper import search_anime_scraper, get_episodes_scraper
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
        logger.info(f"كاش غير متوفر للبحث: '{query}'. جاري الاستعلام من AniList GraphQL...")
        status_msg = await message.answer("🔍 جاري تهيئة البحث باستخدام AniList...")
        try:
            anilist_results = await search_anilist(query)
            await message.bot.delete_message(chat_id=message.chat.id, message_id=status_msg.message_id)
            
            if not anilist_results:
                logger.info(f"AniList لم ترجع نتائج للبحث: '{query}'. جاري الانتقال للبحث في WitAnime...")
                # Native Fallback search to WitAnime
                status_msg = await message.answer("🔍 لم يتم العثور على نتائج في AniList. جاري البحث في WitAnime...")
                scraper_results = await search_anime_scraper(query)
                await message.bot.delete_message(chat_id=message.chat.id, message_id=status_msg.message_id)
                
                if not scraper_results:
                    logger.info(f"WitAnime لم ترجع نتائج للبحث: '{query}'")
                    await message.answer("❌ لم يتم العثور على أنمي مطابق في خوادم البث المساعدة. يرجى التحقق من الاسم المكتوب.")
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
            
            # Cache all resolved results (up to 5)
            logger.info(f"كاش جديد للبحث '{query}' يحتوي على {len(resolved_anime)} نتائج.")
            for anime in resolved_anime[:5]:
                new_cache = SearchCache(
                    query_text=query,
                    anilist_id=anime["anilist_id"],
                    title_english=anime["title_english"],
                    title_romaji=anime["title_romaji"],
                    description=anime["description"],
                    image_url=anime["image_url"],
                    duration=anime.get("duration")
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

    status_msg = await callback.message.answer("🔍 جاري جلب قائمة الحلقات...")
    
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
            search_title = cache_entry.title_romaji or cache_entry.title_english
            scraper_results = await search_anime_scraper(search_title)
            if not scraper_results and cache_entry.title_english and cache_entry.title_english != cache_entry.title_romaji:
                scraper_results = await search_anime_scraper(cache_entry.title_english)
            if not scraper_results:
                await status_msg.edit_text("❌ لم يتم العثور على هذا الأنمي في خوادم البث المساعدة.")
                return
            from app.utils.match import get_best_slug_match
            anime_slug = get_best_slug_match(scraper_results, search_title)

    scraped_data = None
    if anime_slug:
        # Scrape and cache episodes
        scraped_data = await get_episodes_scraper(anime_slug)
        if not scraped_data or not scraped_data.get("episodes"):
            await status_msg.edit_text("❌ فشل في جلب قائمة الحلقات من سيرفر البث المساعد.")
            return
            
        episodes_list = scraped_data["episodes"]
        
        # If database cache lacks high-res details, update them
        updated = False
        if scraped_data.get("poster_url") and (not cache_entry.image_url or "default" in cache_entry.image_url):
            cache_entry.image_url = scraped_data["poster_url"]
            updated = True
        if scraped_data.get("description") and (not cache_entry.description or "نتائج بحث" in cache_entry.description or cache_entry.description == "لا يوجد"):
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

    # Load final episode list from DB
    stmt_eps = select(EpisodeCache).where(EpisodeCache.anilist_id == anilist_id)
    res_eps = await db_session.execute(stmt_eps)
    cached_episodes = res_eps.scalars().all()

    if not cached_episodes:
        await status_msg.edit_text("❌ فشل في تحميل الحلقات من قاعدة البيانات.")
        return

    # Calculate max_episode
    ep_numbers = []
    for ep in cached_episodes:
        try:
            ep_numbers.append(float(ep.ep_number))
        except ValueError:
            pass
            
    if ep_numbers:
        max_episode = int(max(ep_numbers))
    else:
        max_episode = len(cached_episodes)
        
    await callback.bot.delete_message(chat_id=callback.message.chat.id, message_id=status_msg.message_id)
    
    # Store details in FSM context
    await state.update_data(
        anilist_id=anilist_id,
        anime_title=title,
        title_romaji=cache_entry.title_romaji,
        title_english=cache_entry.title_english,
        duration=cache_entry.duration or (scraped_data.get("duration") if scraped_data else None)
    )
    
    # Transition to waiting for episode number
    await state.set_state(SearchStates.waiting_for_episode)
    await callback.answer()

    details_text = (
        f"🎬 **الأنمي المختار**: {title}\n"
        f"📝 القصة: {cache_entry.description[:250] + '...' if cache_entry.description else 'لا يوجد'}\n\n"
        f"الرجاء كتابة رقم الحلقة التي تريدها من 1 إلى {max_episode} (آخر حلقة نزلت حالياً هي {max_episode}):"
    )
    
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ إضافة إلى المفضلة", callback_data=f"fav_add:{anilist_id}")]
    ])
    
    if cache_entry.image_url:
        await callback.message.answer_photo(
            photo=cache_entry.image_url,
            caption=details_text,
            reply_markup=markup,
            parse_mode="Markdown"
        )
    else:
        await callback.message.answer(
            details_text,
            reply_markup=markup,
            parse_mode="Markdown"
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

