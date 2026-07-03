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
    cached = res.scalar_one_or_none()

    resolved_anime = []

    # If cached and not expired (24h)
    if cached and (datetime.now(timezone.utc) - cached.created_at) < timedelta(hours=CACHE_EXPIRATION_HOURS):
        logger.info(f"وجدت كاش للبحث: '{query}' (معرف أنيليست: {cached.anilist_id})")
        resolved_anime.append({
            "anilist_id": cached.anilist_id,
            "title_english": cached.title_english,
            "title_romaji": cached.title_romaji,
            "description": cached.description,
            "image_url": cached.image_url
        })
    else:
        logger.info(f"كاش غير متوفر للبحث: '{query}'. جاري الاستعلام من AniList GraphQL...")
        status_msg = await message.answer("🔍 جاري تهيئة البحث باستخدام AniList...")
        try:
            anilist_results = await search_anilist(query)
            await status_msg.delete()
            
            if not anilist_results:
                logger.info(f"AniList لم ترجع نتائج للبحث: '{query}'. جاري الانتقال للبحث في WitAnime...")
                # Native Fallback search to WitAnime
                status_msg = await message.answer("🔍 لم يتم العثور على نتائج في AniList. جاري البحث في WitAnime...")
                scraper_results = await search_anime_scraper(query)
                await status_msg.delete()
                
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
            
            # Cache the top result
            top_result = resolved_anime[0]
            if cached:
                logger.info(f"تحديث الكاش المنتهي للبحث: '{query}'")
                cached.anilist_id = top_result["anilist_id"]
                cached.title_english = top_result["title_english"]
                cached.title_romaji = top_result["title_romaji"]
                cached.description = top_result["description"]
                cached.image_url = top_result["image_url"]
                cached.created_at = datetime.now(timezone.utc)
            else:
                logger.info(f"إنشاء كاش جديد للبحث: '{query}'")
                new_cache = SearchCache(
                    query_text=query,
                    anilist_id=top_result["anilist_id"],
                    title_english=top_result["title_english"],
                    title_romaji=top_result["title_romaji"],
                    description=top_result["description"],
                    image_url=top_result["image_url"]
                )
                db_session.add(new_cache)
            await db_session.commit()
            
        except Exception as e:
            logger.exception("خطأ أثناء معالجة البحث وتطبيع الاستعلام")
            try:
                await status_msg.delete()
            except Exception:
                pass
            await message.answer(f"❌ حدث خطأ أثناء البحث: {e}")
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
            anime_slug = scraper_results[0]["slug"]

    if anime_slug:
        # Scrape and cache episodes
        scraped_eps = await get_episodes_scraper(anime_slug)
        if not scraped_eps:
            await status_msg.edit_text("❌ فشل في جلب قائمة الحلقات من سيرفر البث المساعد.")
            return
            
        # Delete old cache
        stmt_del = select(EpisodeCache).where(EpisodeCache.anilist_id == anilist_id)
        res_del = await db_session.execute(stmt_del)
        old_eps = res_del.scalars().all()
        for old_ep in old_eps:
            await db_session.delete(old_ep)
            
        # Add new episodes to cache
        for ep in scraped_eps:
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
        
    await status_msg.delete()
    
    # Store details in FSM context
    await state.update_data(
        anilist_id=anilist_id,
        anime_title=title,
        title_romaji=cache_entry.title_romaji,
        title_english=cache_entry.title_english
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
        await callback.answer(f"❌ فشل الحفظ: {e}", show_alert=True)

