import os
import re
from datetime import datetime, timedelta, timezone
from typing import Optional
from config import config
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.exceptions import TelegramBadRequest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.handlers.search import SearchStates
from app.database.models import EpisodeCache, DownloadCache, SearchCache
from app.services.scraper import search_anime_scraper, get_episodes_scraper, get_download_links_scraper
from app.services.downloader import process_and_send_video
from app.utils.logging_config import logger

router = Router(name="download")

CACHE_EXPIRATION_HOURS = 24

@router.message(SearchStates.waiting_for_episode)
async def process_episode_selection(message: Message, db_session: AsyncSession, state: FSMContext):
    """
    Handles user entering episode numbers. Scrapes episodes,
    verifies if requested episode exists, resolves mirror download links,
    and displays quality options.
    """
    requested_ep = message.text.strip()
    
    # Retrieve stored search details
    state_data = await state.get_data()
    anilist_id = state_data.get("anilist_id")
    anime_title = state_data.get("anime_title")
    title_romaji = state_data.get("title_romaji")
    title_english = state_data.get("title_english")
    duration = state_data.get("duration")
    
    if not anilist_id:
        logger.error("خطأ: تم فقدان سياق الحالة FSM أثناء اختيار الحلقة.")
        await message.answer("❌ خطأ: تم فقدان سياق البحث. يرجى البحث عن الأنمي مجدداً.")
        await state.clear()
        return

    logger.info(f"بدء تحليل الحلقة للأنمي '{anime_title}' (معرف أنيليست: {anilist_id}، الحلقة: {requested_ep})")

    status_msg = await message.answer("🔍 جاري التحقق من الحلقات...")
    
    try:
        # Check database EpisodeCache first
        stmt = select(EpisodeCache).where(EpisodeCache.anilist_id == anilist_id)
        res = await db_session.execute(stmt)
        cached_episodes = res.scalars().all()
        
        episodes_list = []
        
        if cached_episodes and (datetime.now(timezone.utc) - cached_episodes[0].created_at) < timedelta(hours=CACHE_EXPIRATION_HOURS):
            logger.info(f"تم العثور على قائمة الحلقات في الكاش لمعرف: {anilist_id}")
            episodes_list = [
                {"ep_number": ep.ep_number, "play_url": ep.play_url}
                for ep in cached_episodes
            ]
        else:
            logger.info(f"الكاش غير متوفر لقائمة الحلقات لمعرف: {anilist_id}. جاري جلب الصفحة...")
            
            # Resolve slug
            anime_slug = None
            if title_romaji and title_romaji.startswith("WITANIME:"):
                anime_slug = title_romaji.split(":", 1)[1]
            else:
                # Search slug on scraper
                search_title = title_romaji or title_english
                scraper_results = await search_anime_scraper(search_title)
                
                if not scraper_results:
                    if title_english and title_english != title_romaji:
                        logger.info(f"فشل البحث بالروماجي. إعادة المحاولة بالإنجليزية: {title_english}")
                        scraper_results = await search_anime_scraper(title_english)
                        
                if not scraper_results:
                    logger.warning(f"لم يتم العثور على الأنمي '{search_title}' في WitAnime.")
                    await status_msg.edit_text("❌ لم يتم العثور على هذا الأنمي في خوادم البث المساعدة.")
                    await state.clear()
                    return
                from app.utils.match import get_best_slug_match
                anime_slug = get_best_slug_match(scraper_results, search_title)
            
            logger.info(f"اسم الأنمي اللطيف (Slug) على WitAnime: '{anime_slug}'")
            
            scraped_eps = await get_episodes_scraper(anime_slug)
            if not scraped_eps:
                logger.error(f"فشل في تحليل الحلقات للاسم اللطيف: {anime_slug}")
                await status_msg.edit_text("❌ فشل في جلب قائمة الحلقات من سيرفر البث.")
                await state.clear()
                return
                
            episodes_list = scraped_eps
            
            # Clear old cache
            if cached_episodes:
                logger.info(f"حذف الكاش القديم للحلقات لمعرف: {anilist_id}")
                for old_ep in cached_episodes:
                    await db_session.delete(old_ep)
            
            # Cache new list
            logger.info(f"حفظ {len(episodes_list)} حلقة في الكاش لمعرف: {anilist_id}")
            for ep in episodes_list:
                db_ep = EpisodeCache(
                    anilist_id=anilist_id,
                    ep_number=ep["ep_number"],
                    play_url=ep["play_url"]
                )
                db_session.add(db_ep)
            await db_session.commit()
            
        # Match user's input with the episodes list
        matched_ep = None
        norm_req = requested_ep.lstrip("0") or "0"
        
        for ep in episodes_list:
            norm_ep = ep["ep_number"].lstrip("0") or "0"
            if norm_req == norm_ep or requested_ep == ep["ep_number"]:
                matched_ep = ep
                break
                
        if not matched_ep:
            logger.info(f"الحلقة {requested_ep} غير موجودة في القائمة المستخرجة.")
            ep_numbers = [e["ep_number"] for e in episodes_list]
            if len(ep_numbers) > 10:
                available_range = f"من `{ep_numbers[0]}` إلى `{ep_numbers[-1]}`"
            else:
                available_range = ", ".join([f"`{n}`" for n in ep_numbers])
                
            await status_msg.edit_text(
                f"❌ لم يتم العثور على الحلقة `{requested_ep}`.\n"
                f"الحلقات المتاحة: {available_range}.\n\n"
                f"🔢 **يرجى إدخال رقم حلقة صحيح:**",
                parse_mode="Markdown"
            )
            return

        play_url = matched_ep["play_url"]
        logger.info(f"تطابق الحلقة {matched_ep['ep_number']}: رابط المشاهدة هو {play_url}")
        
        # Check download cache and prompt quality
        await prompt_quality_selection(
            bot=message.bot,
            chat_id=message.chat.id,
            anilist_id=anilist_id,
            ep_number=matched_ep["ep_number"],
            play_url=play_url,
            anime_title=anime_title,
            duration=duration,
            db_session=db_session
        )
        try:
            await message.bot.delete_message(chat_id=message.chat.id, message_id=status_msg.message_id)
        except Exception:
            pass
        await state.clear()
        
    except Exception:
        logger.exception("خطأ أثناء معالجة اختيار الحلقة")
        await status_msg.edit_text("❌ حدث خطأ أثناء معالجة التحميل. يرجى المحاولة مجدداً.")
        await state.clear()


async def prompt_quality_selection(
    bot,
    chat_id: int,
    anilist_id: int,
    ep_number: str,
    play_url: str,
    anime_title: str,
    duration: Optional[str],
    db_session: AsyncSession,
    message_id: Optional[int] = None
):
    # Check download cache
    dl_stmt = select(DownloadCache).where(DownloadCache.play_url == play_url)
    dl_res = await db_session.execute(dl_stmt)
    cached_dl = dl_res.scalar_one_or_none()
    
    qualities = {}
    db_cache_id = None
    
    if cached_dl and (datetime.now(timezone.utc) - cached_dl.created_at) < timedelta(hours=CACHE_EXPIRATION_HOURS):
        qualities = cached_dl.qualities
        db_cache_id = cached_dl.id
    else:
        status_msg_id = None
        if message_id:
            try:
                await bot.edit_message_text(
                    "🔄 جاري استخراج روابط التحميل المباشرة للحلقة...",
                    chat_id=chat_id,
                    message_id=message_id
                )
                status_msg_id = message_id
            except TelegramBadRequest:
                try:
                    await bot.edit_message_caption(
                        chat_id=chat_id,
                        message_id=message_id,
                        caption="🔄 جاري استخراج روابط التحميل المباشرة للحلقة..."
                    )
                    status_msg_id = message_id
                except Exception:
                    pass
        
        if not status_msg_id:
            status_msg = await bot.send_message(chat_id, "🔄 جاري استخراج روابط التحميل المباشرة للحلقة...")
            status_msg_id = status_msg.message_id
            
        scraped_links = await get_download_links_scraper(play_url)
        
        if not scraped_links:
            try:
                await bot.edit_message_text("❌ فشل في استخراج روابط التحميل لهذه الحلقة. يرجى المحاولة لاحقاً.", chat_id=chat_id, message_id=status_msg_id)
            except TelegramBadRequest:
                try:
                    await bot.edit_message_caption(chat_id=chat_id, message_id=status_msg_id, caption="❌ فشل في استخراج روابط التحميل لهذه الحلقة. يرجى المحاولة لاحقاً.")
                except Exception:
                    pass
            return
            
        qualities = scraped_links
        if cached_dl:
            cached_dl.qualities = qualities
            cached_dl.duration = duration
            cached_dl.created_at = datetime.now(timezone.utc)
            db_session.add(cached_dl)
            await db_session.commit()
            db_cache_id = cached_dl.id
        else:
            new_dl = DownloadCache(
                play_url=play_url,
                qualities=qualities,
                duration=duration
            )
            db_session.add(new_dl)
            await db_session.commit()
            db_cache_id = new_dl.id
            
        # Only delete status_msg if we created a new message
        if status_msg_id != message_id:
            try:
                await bot.delete_message(chat_id, status_msg_id)
            except Exception:
                pass
            
    keyboard_buttons = []
    
    import os
    from aiogram.types import WebAppInfo
    webapp_domain = config.WEBAPP_BASE_URL or os.getenv("RAILWAY_PUBLIC_DOMAIN", "")
    if webapp_domain and not webapp_domain.startswith("http"):
        webapp_domain = f"https://{webapp_domain}"
        
    if webapp_domain:
        q_webapp_url = f"{webapp_domain}/webapp/qualities?db_cache_id={db_cache_id}&anilist_id={anilist_id}&ep_number={ep_number}"
        keyboard_buttons.append([
            InlineKeyboardButton(text="📱 اختر الجودة في الميني أب (Mini App)", web_app=WebAppInfo(url=q_webapp_url))
        ])

    q_keys = list(qualities.keys())
    import re
    def get_q_res(k):
        m = re.search(r'(\d+)', k)
        return int(m.group(1)) if m else 0
    q_keys.sort(key=get_q_res, reverse=True)
    
    row = []
    for q_name in q_keys:
        row.append(InlineKeyboardButton(text=f"⚙️ {q_name}", callback_data=f"dl:{q_name}:{db_cache_id}"))
        if len(row) == 2:
            keyboard_buttons.append(row)
            row = []
    if row:
        keyboard_buttons.append(row)
        
    keyboard_buttons.append([
        InlineKeyboardButton(text="🔙 رجوع للحلقات", callback_data=f"nav_grid:{anilist_id}")
    ])
    markup = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    
    quality_text = (
        f"**الأنمي**: {anime_title}\n"
        f"**الحلقة**: {ep_number}\n\n"
        f"اختر جودة التحميل المفضلة أدناه:"
    )
    
    # Try in-place editing first to avoid chat clutter
    if message_id:
        try:
            try:
                await bot.edit_message_text(
                    quality_text,
                    chat_id=chat_id,
                    message_id=message_id,
                    reply_markup=markup,
                    parse_mode="Markdown"
                )
                return
            except TelegramBadRequest as e:
                if "there is no caption" in str(e).lower() or "message is not modified" in str(e).lower() or "can't edit" in str(e).lower():
                    await bot.edit_message_caption(
                        chat_id=chat_id,
                        message_id=message_id,
                        caption=quality_text,
                        reply_markup=markup,
                        parse_mode="Markdown"
                    )
                    return
                else:
                    raise
        except Exception:
            pass
    
    await bot.send_message(
        chat_id,
        quality_text,
        reply_markup=markup,
        parse_mode="Markdown"
    )


@router.callback_query(F.data.startswith("dl:"))
async def handle_download_callback(callback: CallbackQuery, db_session: AsyncSession):
    """
    Triggers download from selected quality or enqueues task in PersistentTaskQueue.
    """
    parts = callback.data.split(":")
    requested_quality = parts[1]
    cache_id = int(parts[2])
    
    # Retrieve download cache
    stmt = select(DownloadCache).where(DownloadCache.id == cache_id)
    res = await db_session.execute(stmt)
    dl_cache = res.scalar_one_or_none()
    
    if not dl_cache:
        await callback.answer("❌ انتهت صلاحية رابط تحميل الحلقة. يرجى إعادة البحث.", show_alert=True)
        return
        
    await callback.answer()
    
    # Resolve anilist_id and anime_title/ep_num
    play_url = dl_cache.play_url
    anilist_id = None
    anime_title = "أنمي"
    episode_num = ""
    
    stmt_ep = select(EpisodeCache).where(EpisodeCache.play_url == play_url)
    res_ep = await db_session.execute(stmt_ep)
    ep_entry = res_ep.scalars().first()
    if ep_entry:
        anilist_id = ep_entry.anilist_id
        episode_num = ep_entry.ep_number
        stmt_search = select(SearchCache).where(SearchCache.anilist_id == anilist_id)
        res_search = await db_session.execute(stmt_search)
        search_cache = res_search.scalars().first()
        if search_cache:
            anime_title = search_cache.title_english or search_cache.title_romaji
            if anime_title.startswith("WITANIME:"):
                anime_title = search_cache.title_english
                
    if not anilist_id:
        anilist_id = dl_cache.id

    from app.services.downloader import select_best_quality
    # Optimization: Zero-second delivery if already cached as Telegram file ID
    selected_q, download_url, size = await select_best_quality(dl_cache.qualities, requested_quality)
    if not download_url.startswith("http"):
        from app.services.worker import execute_queued_task
        from app.database.connection import AsyncSessionLocal
        await execute_queued_task(
            task_id=0,
            user_id=callback.from_user.id,
            chat_id=callback.message.chat.id,
            status_msg_id=None,
            anilist_id=anilist_id,
            anime_title=anime_title,
            episode_num=episode_num,
            requested_quality=requested_quality,
            bot=callback.bot,
            db_session_factory=AsyncSessionLocal
        )
        return

    # Create status message in-place
    status_text = (
        f"⏳ **تم إضافة طلبك لقائمة الانتظار:**\n"
        f"🎬 الأنمي: {anime_title}\n"
        f"🔢 الحلقة: {episode_num}\n"
        f"⚙️ الجودة: {requested_quality}\n\n"
        f"🔄 جاري بدء المعالجة والتحميل، يرجى الانتظار..."
    )
    try:
        await callback.message.edit_text(status_text, reply_markup=None, parse_mode="Markdown")
    except TelegramBadRequest:
        try:
            await callback.message.edit_caption(caption=status_text, reply_markup=None, parse_mode="Markdown")
        except Exception:
            pass

    # Insert into PersistentTaskQueue
    from app.database.models import PersistentTaskQueue
    new_task = PersistentTaskQueue(
        user_id=callback.from_user.id,
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
        anilist_id=anilist_id,
        anime_title=anime_title,
        episode_num=episode_num,
        quality=requested_quality,
        status="pending"
    )
    db_session.add(new_task)
    await db_session.commit()
    logger.info(f"Enqueued download task {new_task.id} for User {callback.from_user.id}")


@router.callback_query(F.data.startswith("nav_ep:"))
async def handle_nav_ep(callback: CallbackQuery, db_session: AsyncSession):
    parts = callback.data.split(":")
    anilist_id = int(parts[1])
    ep_num = parts[2]
    
    await callback.answer()
    
    # Retrieve play_url
    stmt = select(EpisodeCache).where(
        (EpisodeCache.anilist_id == anilist_id) & (EpisodeCache.ep_number == ep_num)
    )
    res = await db_session.execute(stmt)
    ep_entry = res.scalar_one_or_none()
    if not ep_entry:
        try:
            await callback.message.edit_text("❌ عذراً، لم يتم العثور على الحلقة المطلوبة في الكاش.")
        except TelegramBadRequest:
            await callback.message.answer("❌ عذراً، لم يتم العثور على الحلقة المطلوبة في الكاش.")
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


@router.callback_query(F.data.startswith("nav_grid:"))
async def handle_nav_grid(callback: CallbackQuery, db_session: AsyncSession):
    parts = callback.data.split(":")
    anilist_id = int(parts[1])
    
    await callback.answer()
    
    from app.handlers.search import render_episode_keyboard
    await render_episode_keyboard(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
        anilist_id=anilist_id,
        db_session=db_session
    )

