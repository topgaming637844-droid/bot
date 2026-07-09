import asyncio
import os
import aiohttp
import time
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict

from aiogram import Bot
from aiogram.types import FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup, BufferedInputFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import config
from app.database.models import PersistentTaskQueue, EpisodeCache, DownloadCache, AnimeTopicCache
from app.utils.logging_config import logger
from app.services.scraper import get_download_links_scraper
from app.services.downloader import select_best_quality, parse_duration_to_seconds, download_file

# Concurrency semaphore for FFmpeg to prevent CPU/RAM exhaustion (1 compression task at a time)
ffmpeg_semaphore = asyncio.Semaphore(1)

def make_hashtag(title_str: str) -> str:
    """Sanitizes anime title into a safe Arabic-friendly hashtag."""
    cleaned = re.sub(r'[^\w\s]', '', title_str)
    cleaned = re.sub(r'\s+', '_', cleaned)
    return cleaned

def prepare_telegram_thumbnail(raw_file_path: Path, target_jpg_path: Path) -> bool:
    """Ensures image is resized to <=320px, JPEG format, and <200KB for Telegram API requirements."""
    try:
        from PIL import Image
        with Image.open(raw_file_path) as img:
            img = img.convert("RGB")
            img.thumbnail((320, 320), Image.Resampling.LANCZOS)
            img.save(target_jpg_path, "JPEG", quality=85, optimize=True)
            logger.info(f"Prepared compliant Telegram video thumbnail: {target_jpg_path} ({target_jpg_path.stat().st_size} bytes)")
            return True
    except Exception as e:
        logger.warning(f"PIL failed to format thumbnail: {e}. Attempting FFmpeg fallback...")
        try:
            import subprocess
            cmd = [
                "ffmpeg", "-y", "-i", str(raw_file_path),
                "-vf", "scale='min(320,iw)':-1",
                "-vframes", "1",
                "-q:v", "2",
                str(target_jpg_path)
            ]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
            if target_jpg_path.exists() and target_jpg_path.stat().st_size > 0:
                logger.info(f"Prepared thumbnail via FFmpeg: {target_jpg_path}")
                return True
        except Exception as ff_e:
            logger.warning(f"FFmpeg thumbnail fallback failed: {ff_e}")
    return False

async def get_video_metadata(video_path: Path) -> tuple[Optional[int], Optional[int], Optional[int]]:
    """Returns (duration, width, height) of the video file using ffprobe."""
    try:
        import json
        cmd = [
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_streams", "-show_format", str(video_path)
        ]
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        if process.returncode == 0:
            data = json.loads(stdout.decode('utf-8'))
            duration = None
            width = None
            height = None
            
            if "format" in data and "duration" in data["format"]:
                try: duration = int(float(data["format"]["duration"]))
                except ValueError: pass
                
            for stream in data.get("streams", []):
                if stream.get("codec_type") == "video":
                    if "width" in stream:
                        width = int(stream["width"])
                    if "height" in stream:
                        height = int(stream["height"])
                    if not duration and "duration" in stream:
                        try: duration = int(float(stream["duration"]))
                        except ValueError: pass
                    break
            return duration, width, height
    except Exception as e:
        logger.warning(f"Failed to probe video metadata using ffprobe: {e}")
    return None, None, None

async def get_thumbnail_input(bot: Bot) -> Optional[FSInputFile]:
    """Helper to retrieve, format, and prepare custom thumbnail from Telegram as active FSInputFile object."""
    from app.utils.settings import get_setting
    file_id = await get_setting("custom_thumb_file_id")
    if not file_id:
        return None
        
    sanitized_id = re.sub(r'[^a-zA-Z0-9]', '_', str(file_id))[:15]
    raw_path = config.DOWNLOAD_DIR / f"raw_thumb_{sanitized_id}.jpg"
    optimized_path = config.DOWNLOAD_DIR / f"custom_thumb_320_{sanitized_id}.jpg"
    
    if optimized_path.exists() and optimized_path.stat().st_size > 0:
        return FSInputFile(str(optimized_path))
        
    try:
        logger.info(f"Downloading/Retrieving custom thumbnail file from Telegram file_id: {file_id}")
        file_info = await bot.get_file(file_id)
        if file_info and file_info.file_path:
            # 1. Check if it's a local file and exists (Shared Volume / Same Container setup)
            local_file_path = Path(file_info.file_path)
            if local_file_path.is_absolute() and local_file_path.exists():
                logger.info(f"Local file system hit: Copying custom thumbnail directly from {local_file_path}")
                import shutil
                os.makedirs(os.path.dirname(raw_path), exist_ok=True)
                shutil.copy2(local_file_path, raw_path)
            else:
                # 2. Fallback to direct HTTP download from custom local or official API
                file_path = file_info.file_path
                # Extract standard relative path if Bot API server is running in local mode and returns absolute disk path
                if "/" in file_path:
                    for prefix in ["photos/", "documents/", "video/", "voice/", "stickers/", "music/"]:
                        if prefix in file_path:
                            file_path = prefix + file_path.split(prefix, 1)[1]
                            break
                
                os.makedirs(os.path.dirname(raw_path), exist_ok=True)
                
                # Determine URLs to attempt downloading from
                dl_urls = []
                if config.TELEGRAM_API_SERVER:
                    dl_urls.append(f"{config.TELEGRAM_API_SERVER}/file/bot{config.BOT_TOKEN}/{file_path}")
                dl_urls.append(f"https://api.telegram.org/file/bot{config.BOT_TOKEN}/{file_path}")
                
                downloaded = False
                async with aiohttp.ClientSession() as session:
                    for dl_url in dl_urls:
                        try:
                            logger.info(f"Downloading custom thumbnail from Telegram path: {dl_url}")
                            async with session.get(dl_url, timeout=30) as resp:
                                if resp.status == 200:
                                    with open(raw_path, "wb") as f:
                                        f.write(await resp.read())
                                    downloaded = True
                                    break
                                else:
                                    logger.warning(f"Failed download from {dl_url} status: {resp.status}")
                        except Exception as dl_e:
                            logger.warning(f"Error downloading from {dl_url}: {dl_e}")
                            
                if not downloaded:
                    raise Exception("Failed to download custom thumbnail from all URLs")
            
            if raw_path.exists() and raw_path.stat().st_size > 0:
                success = prepare_telegram_thumbnail(raw_path, optimized_path)
                final_path = optimized_path if (success and optimized_path.exists()) else raw_path
                return FSInputFile(str(final_path))
    except Exception as e:
        logger.warning(f"Failed to download/process custom thumbnail from Telegram: {e}")
        
    return None

async def get_video_thumbnail(bot: Bot, db_session_factory, anilist_id: int) -> Optional[FSInputFile]:
    """Retrieves custom admin thumbnail strictly and exclusively as video cover art."""
    return await get_thumbnail_input(bot)

async def save_telegram_file_cache(db_session_factory, anilist_id: int, ep_number: str, quality: str, file_id: str, file_size_mb: Optional[float] = None):
    """Persists Telegram file_id and real file size in MB to TelegramFileCache table for zero-second instant delivery."""
    try:
        from app.database.models import TelegramFileCache
        async with db_session_factory() as session:
            stmt = select(TelegramFileCache).where(
                (TelegramFileCache.anilist_id == anilist_id) &
                (TelegramFileCache.ep_number == ep_number) &
                (TelegramFileCache.quality == quality)
            )
            res = await session.execute(stmt)
            existing = res.scalar_one_or_none()
            if existing:
                existing.file_id = file_id
                if file_size_mb and file_size_mb > 0:
                    existing.file_size = file_size_mb
            else:
                new_entry = TelegramFileCache(
                    anilist_id=anilist_id,
                    ep_number=ep_number,
                    quality=quality,
                    file_id=file_id,
                    file_size=file_size_mb
                )
                session.add(new_entry)
            await session.commit()
            logger.info(f"Saved TelegramFileCache entry for anilist_id={anilist_id}, ep={ep_number}, quality={quality}, size={file_size_mb} MB")
    except Exception as e:
        logger.exception(f"Error saving to TelegramFileCache: {e}")

async def enqueue_persistent_download_task(
    db_session_factory,
    bot: Bot,
    user_id: int,
    chat_id: int,
    message_id: Optional[int],
    anilist_id: int,
    anime_title: str,
    episode_num: str,
    quality: str = "720p"
) -> PersistentTaskQueue:
    """Enqueues a new download task into PersistentTaskQueue."""
    async with db_session_factory() as session:
        new_task = PersistentTaskQueue(
            user_id=user_id,
            chat_id=chat_id,
            message_id=message_id,
            anilist_id=anilist_id,
            anime_title=anime_title,
            episode_num=episode_num,
            quality=quality,
            status="pending"
        )
        session.add(new_task)
        await session.commit()
        logger.info(f"Enqueued persistent download task {new_task.id} for User {user_id}: {anime_title} Ep {episode_num}")
        return new_task

async def acquire_lock(anilist_id: int, ep_number: str, task_id: int, db_session_factory) -> bool:
    """Attempts to acquire an exclusive processing lock for (anilist_id, ep_number). Returns True if acquired."""
    from app.database.models import DownloadLock
    from sqlalchemy.exc import IntegrityError
    try:
        async with db_session_factory() as session:
            stmt = select(DownloadLock).where(
                (DownloadLock.anilist_id == anilist_id) &
                (DownloadLock.ep_number == str(ep_number))
            )
            res = await session.execute(stmt)
            existing_lock = res.scalar_one_or_none()
            
            if existing_lock:
                if existing_lock.locked_at:
                    delta = (datetime.now(timezone.utc) - existing_lock.locked_at).total_seconds()
                    if delta > 1200:
                        logger.warning(f"Clearing expired lock on anilist_id={anilist_id}, ep={ep_number} (age: {delta:.0f}s)")
                        await session.delete(existing_lock)
                        await session.commit()
                    else:
                        return False
                else:
                    return False
                    
            lock = DownloadLock(anilist_id=anilist_id, ep_number=str(ep_number), task_id=task_id)
            session.add(lock)
            await session.commit()
            logger.info(f"Acquired DownloadLock for anilist_id={anilist_id}, ep={ep_number} by task {task_id}")
            return True
    except (IntegrityError, Exception) as e:
        logger.info(f"Lock already held for anilist_id={anilist_id}, ep={ep_number}: {e}")
        return False

async def release_lock(anilist_id: int, ep_number: str, db_session_factory) -> None:
    """Releases the processing lock for (anilist_id, ep_number)."""
    from app.database.models import DownloadLock
    try:
        async with db_session_factory() as session:
            stmt = select(DownloadLock).where(
                (DownloadLock.anilist_id == anilist_id) &
                (DownloadLock.ep_number == str(ep_number))
            )
            res = await session.execute(stmt)
            lock = res.scalar_one_or_none()
            if lock:
                await session.delete(lock)
                await session.commit()
                logger.info(f"Released DownloadLock for anilist_id={anilist_id}, ep={ep_number}")
    except Exception as e:
        logger.warning(f"Error releasing lock for anilist_id={anilist_id}, ep={ep_number}: {e}")

async def recover_stuck_tasks(db_session_factory):
    """Resets any 'processing' tasks back to 'pending' on startup and clears all locks."""
    try:
        from app.database.models import DownloadLock
        from sqlalchemy import delete
        async with db_session_factory() as session:
            try:
                await session.execute(delete(DownloadLock))
            except Exception as lock_clean_err:
                logger.warning(f"Note: Could not clear DownloadLock table on boot: {lock_clean_err}")
                
            stmt = select(PersistentTaskQueue).where(PersistentTaskQueue.status == "processing")
            res = await session.execute(stmt)
            stuck_tasks = res.scalars().all()
            for task in stuck_tasks:
                task.status = "pending"
                logger.info(f"Recovering stuck task {task.id} (status: processing) on boot. Resetting to 'pending'.")
            await session.commit()
    except Exception as e:
        logger.exception(f"Error recovering stuck tasks on boot: {e}")

async def process_task_with_timeout(
    task_id, user_id, chat_id, message_id, anilist_id, anime_title, episode_num, quality, bot,
    db_session_factory
):
    success = False
    is_locked_wait = False
    try:
        result = await asyncio.wait_for(
            execute_queued_task(
                task_id, user_id, chat_id, message_id, anilist_id, anime_title, episode_num, quality, bot, db_session_factory
            ),
            timeout=1200  # 20 minutes max for slow connections
        )
        if result == "LOCKED_WAIT":
            is_locked_wait = True
            success = False
        else:
            success = bool(result)
    except asyncio.TimeoutError:
        logger.error(f"Task {task_id} timed out after 1200 seconds")
        success = False
    except (asyncio.CancelledError, Exception) as e:
        logger.exception(f"Error or cancellation processing task ID {task_id}: {e}")
        success = False
    finally:
        await release_lock(anilist_id, episode_num, db_session_factory)
        try:
            async with db_session_factory() as session:
                stmt = select(PersistentTaskQueue).where(PersistentTaskQueue.id == task_id)
                res = await session.execute(stmt)
                db_task = res.scalar_one_or_none()
                if db_task:
                    if is_locked_wait:
                        db_task.status = "pending"
                        logger.info(f"Task {task_id} waiting on lock, reset status to 'pending'")
                    else:
                        db_task.status = "completed" if success else "failed"
                        logger.info(f"Updated task {task_id} final status to '{db_task.status}'")
                    db_task.updated_at = datetime.now(timezone.utc)
                    await session.commit()
        except Exception as final_err:
            logger.error(f"Failed to update final status for task {task_id}: {final_err}")

async def task_consumer_worker(bot: Bot, db_session_factory):
    """Indefinite background consumer worker loop processing multi-user tasks concurrently."""
    logger.info("Background task consumer worker loop started with multi-user concurrent processing.")
    active_worker_tasks = set()
    MAX_CONCURRENT_WORKER_TASKS = 3

    while True:
        try:
            active_worker_tasks = {t for t in active_worker_tasks if not t.done()}
            if len(active_worker_tasks) < MAX_CONCURRENT_WORKER_TASKS:
                async with db_session_factory() as session:
                    from app.database.models import DownloadLock
                    # Fetch active processing episode combinations
                    stmt_active = select(PersistentTaskQueue.anilist_id, PersistentTaskQueue.episode_num).where(PersistentTaskQueue.status == "processing")
                    res_active = await session.execute(stmt_active)
                    active_pairs = set(res_active.all())

                    stmt_locks = select(DownloadLock.anilist_id, DownloadLock.ep_number)
                    try:
                        res_locks = await session.execute(stmt_locks)
                        active_pairs.update(res_locks.all())
                    except Exception:
                        pass

                    stmt = select(PersistentTaskQueue).where(PersistentTaskQueue.status == "pending").order_by(PersistentTaskQueue.id.asc()).limit(10)
                    res = await session.execute(stmt)
                    pending_tasks = res.scalars().all()
                    
                    candidate_task = None
                    for pt in pending_tasks:
                        if (pt.anilist_id, pt.episode_num) not in active_pairs:
                            candidate_task = pt
                            break
                            
                    if candidate_task:
                        candidate_task.status = "processing"
                        candidate_task.updated_at = datetime.now(timezone.utc)
                        
                        t_id = candidate_task.id
                        u_id = candidate_task.user_id
                        c_id = candidate_task.chat_id
                        m_id = candidate_task.message_id
                        a_id = candidate_task.anilist_id
                        a_title = candidate_task.anime_title
                        ep_num = candidate_task.episode_num
                        q_val = candidate_task.quality
                        
                        await session.commit()
                        
                        worker_task = asyncio.create_task(
                            process_task_with_timeout(
                                t_id, u_id, c_id, m_id, a_id, a_title, ep_num, q_val, bot, db_session_factory
                            )
                        )
                        active_worker_tasks.add(worker_task)
                    else:
                        await asyncio.sleep(2)
            else:
                await asyncio.sleep(1)
        except Exception:
            logger.exception("Error in task consumer loop")
            await asyncio.sleep(3)

async def self_heal_episode_cache(
    anilist_id: int,
    anime_title: str,
    episode_num: str,
    db_session_factory
) -> Optional[EpisodeCache]:
    """
    Self-healing task scraper fallback:
    If lookup for the requested episode inside EpisodeCache returns None or is missing,
    this function re-scrapes the anime details page on the fly and populates EpisodeCache.
    """
    from app.database.models import SearchCache, EpisodeCache
    from app.services.scraper import search_anime_scraper, get_episodes_scraper
    from app.utils.match import get_best_slug_match, sanitize_search_query
    
    logger.info(f"Self-healing: Re-scraping episodes for anilist_id={anilist_id}, title={anime_title}")
    
    # 1. Try to find the anime in SearchCache to get details
    async with db_session_factory() as session:
        stmt = select(SearchCache).where(SearchCache.anilist_id == anilist_id)
        res = await session.execute(stmt)
        cache_entry = res.scalar_one_or_none()
        
        # If no SearchCache entry, we can create a temporary mockup
        if not cache_entry:
            logger.info(f"Self-healing: No SearchCache entry found for anilist_id={anilist_id}. Querying AniList API to resolve details.")
            anilist_data = None
            try:
                from app.services.anilist import get_anime_by_id
                anilist_data = await get_anime_by_id(anilist_id)
            except Exception as e:
                logger.warning(f"Failed to query AniList by ID during self-healing: {e}")
                
            if anilist_data:
                title_english = anilist_data.get("title_english") or anilist_data.get("title_romaji") or anime_title
                title_romaji = anilist_data.get("title_romaji") or title_english
                description = anilist_data.get("description") or "لا يوجد"
                image_url = anilist_data.get("image_url")
                synonyms = anilist_data.get("synonyms") or []
            else:
                title_english = anime_title
                title_romaji = anime_title
                description = "لا يوجد"
                image_url = None
                synonyms = []

            try:
                cache_entry = SearchCache(
                    query_text=anime_title.lower(),
                    anilist_id=anilist_id,
                    title_english=title_english,
                    title_romaji=title_romaji,
                    description=description,
                    image_url=image_url,
                    synonyms=synonyms
                )
                session.add(cache_entry)
                await session.commit()
            except Exception:
                await session.rollback()
                stmt_retry = select(SearchCache).where(SearchCache.anilist_id == anilist_id)
                res_retry = await session.execute(stmt_retry)
                cache_entry = res_retry.scalar_one_or_none()
            
        anime_slug = None
        if cache_entry.title_romaji and cache_entry.title_romaji.startswith("WITANIME:"):
            anime_slug = cache_entry.title_romaji.split(":", 1)[1]
        else:
            from app.services.scraper import resolve_anime_slug_scraper
            anime_slug = await resolve_anime_slug_scraper(
                title_romaji=cache_entry.title_romaji,
                title_english=cache_entry.title_english,
                synonyms=cache_entry.synonyms
            )
            
        if not anime_slug:
            logger.error(f"Self-healing failed: Could not find matching WitAnime slug for {anime_title}")
            return None
            
        # 2. Scrape and populate episodes
        scraped_data = await get_episodes_scraper(anime_slug)
        if not scraped_data or not scraped_data.get("episodes"):
            logger.error(f"Self-healing failed: Scraper returned no episodes for slug {anime_slug}")
            return None
            
        episodes_list = scraped_data["episodes"]
        
        # Update search cache fields if needed
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
            try:
                await session.merge(cache_entry)
                await session.commit()
            except Exception:
                await session.rollback()
            
        # 3. Delete old episodes and write fresh ones
        stmt_del = select(EpisodeCache).where(EpisodeCache.anilist_id == anilist_id)
        res_del = await session.execute(stmt_del)
        old_eps = res_del.scalars().all()
        for old_ep in old_eps:
            await session.delete(old_ep)
            
        for ep in episodes_list:
            db_ep = EpisodeCache(
                anilist_id=anilist_id,
                ep_number=ep["ep_number"],
                play_url=ep["play_url"]
            )
            session.add(db_ep)
        await session.commit()
        
        # 4. Get the requested episode entry
        stmt_final = select(EpisodeCache).where(
            (EpisodeCache.anilist_id == anilist_id) & (EpisodeCache.ep_number == episode_num)
        )
        res_final = await session.execute(stmt_final)
        final_ep = res_final.scalar_one_or_none()
        
        if final_ep:
            return final_ep
            
        # Fallback: Scrape Gogoanime for the missing episode
        logger.info(f"Self-healing: Episode {episode_num} not found on WitAnime. Trying Gogoanime fallback...")
        try:
            from app.services.scraper import search_anime_gogoanime, get_episodes_gogoanime
            from app.utils.match import get_best_slug_match
            search_title = cache_entry.title_romaji or cache_entry.title_english or anime_title
            gogo_results = await search_anime_gogoanime(search_title)
            if gogo_results:
                gogo_slug = get_best_slug_match(gogo_results, search_title)
                if gogo_slug:
                    logger.info(f"Self-healing: Found matching Gogoanime slug '{gogo_slug}'. Scraping Gogoanime episodes...")
                    gogo_scraped = await get_episodes_gogoanime(gogo_slug)
                    if gogo_scraped and gogo_scraped.get("episodes"):
                        for ep in gogo_scraped["episodes"]:
                            # Skip if already exists
                            stmt_check = select(EpisodeCache).where(
                                (EpisodeCache.anilist_id == anilist_id) & (EpisodeCache.ep_number == ep["ep_number"])
                            )
                            check_res = await session.execute(stmt_check)
                            if not check_res.scalar_one_or_none():
                                db_ep = EpisodeCache(
                                    anilist_id=anilist_id,
                                    ep_number=ep["ep_number"],
                                    play_url=ep["play_url"]
                                )
                                session.add(db_ep)
                        await session.commit()
                        
                        # Re-fetch the episode
                        res_final = await session.execute(stmt_final)
                        return res_final.scalar_one_or_none()
        except Exception as e:
            logger.warning(f"Self-healing: Gogoanime fallback failed: {e}")
            
        return None

async def execute_queued_task(
    task_id: int,
    user_id: int,
    chat_id: int,
    status_msg_id: Optional[int],
    anilist_id: int,
    anime_title: str,
    episode_num: str,
    requested_quality: str,
    bot: Bot,
    db_session_factory
) -> bool:
    """Executes HLS segment downloading, compression, delivery, and forum mirroring."""
    temp_file_path = None
    logger.info(f"Executing task {task_id}: {anime_title} ep {episode_num} [{requested_quality}]")
    
    # 0. Check TelegramFileCache for instant Zero-second delivery across server crashes/restarts
    cached_file_id = None
    cached_quality = None
    cached_file_size = None
    try:
        from app.database.models import TelegramFileCache
        async with db_session_factory() as session:
            stmt_tf = select(TelegramFileCache).where(
                (TelegramFileCache.anilist_id == anilist_id) &
                (TelegramFileCache.ep_number == episode_num)
            )
            if requested_quality != "auto":
                stmt_tf = stmt_tf.where(TelegramFileCache.quality == requested_quality)
            res_tf = await session.execute(stmt_tf)
            tf_entry = res_tf.scalars().first()
            if tf_entry:
                cached_file_id = str(tf_entry.file_id)
                cached_quality = str(tf_entry.quality)
                cached_file_size = float(tf_entry.file_size) if tf_entry.file_size else None
    except Exception as tf_err:
        logger.warning(f"Note: TelegramFileCache check skipped: {tf_err}")
        
    if cached_file_id:
        logger.info(f"Zero-second Delivery (DB File ID hit): {cached_file_id[:15]}... for {anime_title} Ep {episode_num} [{cached_quality}]")
        if status_msg_id:
            try: await bot.delete_message(chat_id=chat_id, message_id=status_msg_id)
            except Exception: pass
            
        # Render navigation keyboard
        prev_ep, next_ep = None, None
        async with db_session_factory() as session:
            stmt_all = select(EpisodeCache).where(EpisodeCache.anilist_id == anilist_id)
            res_all = await session.execute(stmt_all)
            all_eps = list(res_all.scalars().all())
            def parse_ep(e):
                try: return float(e.ep_number)
                except ValueError: return 999999.0
            all_eps.sort(key=parse_ep)
            idx = -1
            for i, ep in enumerate(all_eps):
                if ep.ep_number == episode_num:
                    idx = i
                    break
            if idx > 0: prev_ep = all_eps[idx - 1].ep_number
            if idx >= 0 and idx < len(all_eps) - 1: next_ep = all_eps[idx + 1].ep_number
            
        nav_row = []
        if prev_ep: nav_row.append(InlineKeyboardButton(text="◀️ السابقة", callback_data=f"nav_ep:{anilist_id}:{prev_ep}"))
        nav_row.append(InlineKeyboardButton(text="🔢 الحلقات", callback_data=f"nav_grid:{anilist_id}"))
        if next_ep: nav_row.append(InlineKeyboardButton(text="التالية ▶️", callback_data=f"nav_ep:{anilist_id}:{next_ep}"))
        nav_markup = InlineKeyboardMarkup(inline_keyboard=[nav_row])
        
        bot_info = await bot.get_me()
        bot_username = f"@{bot_info.username}" if bot_info else ""
        
        import html
        size_caption = f"{cached_file_size:.1f} MB" if cached_file_size and cached_file_size > 0 else "سريع ⚡"
        caption = (
            f"🎬 <b>{html.escape(anime_title)}</b>\n"
            f"🔢 <b>الحلقة:</b> {episode_num}\n"
            f"⚙️ <b>الجودة:</b> {cached_quality}\n"
            f"💾 <b>الحجم:</b> {size_caption}\n\n"
            f"🎥 <b>مشاهدة ممتعة!</b> ✨🍿\n"
            f"📢 <b>البوت:</b> {bot_username}"
        )
        thumb_input = await get_video_thumbnail(bot, db_session_factory, anilist_id)
        
        try:
            await bot.send_video(
                chat_id=chat_id,
                video=cached_file_id,
                thumbnail=thumb_input,
                caption=caption,
                supports_streaming=True,
                reply_markup=nav_markup,
                parse_mode="HTML"
            )
            return True
        except Exception as cached_deliv_err:
            logger.warning(f"Failed instant delivery of file_id {cached_file_id}: {cached_deliv_err}. Falling back to full scraper pipeline.")

    # 0.5 Acquire exclusive DownloadLock for episode
    lock_acquired = await acquire_lock(anilist_id, episode_num, task_id, db_session_factory)
    if not lock_acquired:
        logger.info(f"Task {task_id} waiting for lock on anilist_id={anilist_id}, ep={episode_num}")
        if status_msg_id:
            try:
                await bot.edit_message_text(
                    "⏳ <b>الحلقة المطلوبة قيد التحضير/التحميل حالياً بواسطة مستخدم آخر.</b>\n\n"
                    "ستصلك الحلقة فور انتهاء معالجتها تلقائياً خلال لحظات... 🍿✨",
                    chat_id=chat_id,
                    message_id=status_msg_id,
                    parse_mode="HTML"
                )
            except Exception:
                pass
        await asyncio.sleep(5)
        return "LOCKED_WAIT"

    # 1. Resolve play_url from EpisodeCache
    async with db_session_factory() as session:
        stmt = select(EpisodeCache).where(
            (EpisodeCache.anilist_id == anilist_id) & (EpisodeCache.ep_number == episode_num)
        )
        res = await session.execute(stmt)
        ep_entry = res.scalar_one_or_none()
        
    if not ep_entry:
        logger.warning(f"Failed to find episode in EpisodeCache for {anilist_id} ep {episode_num}. Triggering self-healing fallback...")
        if status_msg_id:
            try:
                await bot.edit_message_text("⚡ جاري تحضير واستخراج روابط الحلقة من المخدم...", chat_id=chat_id, message_id=status_msg_id)
            except Exception: pass
            
        ep_entry = await self_heal_episode_cache(anilist_id, anime_title, episode_num, db_session_factory)
        
        if not ep_entry:
            logger.error(f"Self-healing failed to find/scrape episode {episode_num} for anilist_id {anilist_id}")
            if status_msg_id:
                try:
                    await bot.edit_message_text("❌ فشل استرداد الحلقة تلقائياً. الرجاء إعادة محاولة البحث.", chat_id=chat_id, message_id=status_msg_id)
                except Exception: pass
            return False
            
    play_url = ep_entry.play_url

    # 2. Get/Scrape Download Links
    qualities = {}
    duration_str = None
    async with db_session_factory() as session:
        stmt_dl = select(DownloadCache).where(DownloadCache.play_url == play_url)
        res_dl = await session.execute(stmt_dl)
        dl_cache = res_dl.scalar_one_or_none()
        if dl_cache:
            qualities = dl_cache.qualities
            duration_str = dl_cache.duration

    if not qualities:
        if status_msg_id:
            try:
                await bot.edit_message_text("🔄 جاري استخراج روابط البث...", chat_id=chat_id, message_id=status_msg_id)
            except Exception: pass
        qualities = await get_download_links_scraper(play_url)
        if not qualities:
            logger.error(f"DIAGNOSTIC: Queue worker failed to resolve qualities for {play_url}. Deep scan returned empty.")
            if status_msg_id:
                inspect_text = (
                    f"❌ <b>فشل استخراج روابط التحميل من خادم البث.</b>\n\n"
                    f"🛠️ يمكن فحص صفحة الحلقة يدوياً عبر هذا الرابط:\n"
                    f"🔗 <a href='{play_url}'>رابط الصفحة المصدر</a>"
                )
                try:
                    await bot.edit_message_text(inspect_text, chat_id=chat_id, message_id=status_msg_id, parse_mode="HTML", disable_web_page_preview=True)
                except Exception:
                    pass
            return False
        # Save to DB cache
        async with db_session_factory() as session:
            try:
                new_dl = DownloadCache(play_url=play_url, qualities=qualities, duration=duration_str)
                session.add(new_dl)
                await session.commit()
            except Exception:
                await session.rollback()

    # 3. Check for cached Telegram file ID (Zero-second Delivery)
    selected_quality, download_url, size = await select_best_quality(qualities, requested_quality)
    
    # Render under-video navigation keyboard
    prev_ep, next_ep = None, None
    async with db_session_factory() as session:
        stmt_all = select(EpisodeCache).where(EpisodeCache.anilist_id == anilist_id)
        res_all = await session.execute(stmt_all)
        all_eps = res_all.scalars().all()
        # Custom float sort
        def parse_ep(e):
            try: return float(e.ep_number)
            except ValueError: return 999999.0
        all_eps.sort(key=parse_ep)
        
        # Find index
        idx = -1
        for i, ep in enumerate(all_eps):
            if ep.ep_number == episode_num:
                idx = i
                break
        if idx > 0:
            prev_ep = all_eps[idx - 1].ep_number
        if idx >= 0 and idx < len(all_eps) - 1:
            next_ep = all_eps[idx + 1].ep_number

    nav_row = []
    if prev_ep:
        nav_row.append(InlineKeyboardButton(text="◀️ السابقة", callback_data=f"nav_ep:{anilist_id}:{prev_ep}"))
    nav_row.append(InlineKeyboardButton(text="🔢 الحلقات", callback_data=f"nav_grid:{anilist_id}"))
    if next_ep:
        nav_row.append(InlineKeyboardButton(text="التالية ▶️", callback_data=f"nav_ep:{anilist_id}:{next_ep}"))
    nav_markup = InlineKeyboardMarkup(inline_keyboard=[nav_row])

    bot_info = await bot.get_me()
    bot_username = f"@{bot_info.username}" if bot_info else ""
    
    size_mb = size / (1024 * 1024)
        
    import html
    caption = (
        f"🎬 <b>{html.escape(anime_title)}</b>\n"
        f"🔢 <b>الحلقة:</b> {episode_num}\n"
        f"⚙️ <b>الجودة:</b> {selected_quality}\n"
        f"💾 <b>الحجم:</b> {size_mb:.1f} MB\n\n"
        f"🎥 <b>مشاهدة ممتعة!</b> ✨🍿\n"
        f"📢 <b>البوت:</b> {bot_username}"
    )

    # If it is a Telegram file ID
    if not download_url.startswith("http"):
        logger.info(f"Zero-second Delivery: Sending cached File ID {download_url}")
        if status_msg_id:
            try: await bot.delete_message(chat_id=chat_id, message_id=status_msg_id)
            except Exception: pass
        
        thumb_input = await get_video_thumbnail(bot, db_session_factory, anilist_id)
        
        await bot.send_video(
            chat_id=chat_id,
            video=download_url,
            thumbnail=thumb_input,
            duration=parse_duration_to_seconds(duration_str),
            caption=caption,
            supports_streaming=True,
            reply_markup=nav_markup,
            parse_mode="HTML"
        )
        await save_telegram_file_cache(db_session_factory, anilist_id, episode_num, selected_quality, download_url)
        return True

    # 4. Download media file
    if status_msg_id:
        try:
            await bot.edit_message_text("📥 جاري تحميل الفيديو من سيرفرات البث...", chat_id=chat_id, message_id=status_msg_id)
        except Exception: pass

    unique_id = f"{user_id}_{uuid.uuid4().hex[:6]}"
    filename = f"anime_{unique_id}_{int(time.time())}_{selected_quality}.mp4"
    temp_file_path = config.DOWNLOAD_DIR / filename

    try:
        # Create a mock status message parameter for the downloader updates
        class StatusMsgProxy:
            def __init__(self, bot_inst, cid, mid):
                self.bot = bot_inst
                self.chat = type('Chat', (), {'id': cid})()
                self.message_id = mid
            async def edit_text(self, text, parse_mode=None):
                try:
                    await self.bot.edit_message_text(text, chat_id=self.chat.id, message_id=self.message_id, parse_mode=parse_mode)
                except Exception: pass

        proxy_msg = StatusMsgProxy(bot, chat_id, status_msg_id)
        
        success = await download_file(download_url, temp_file_path, proxy_msg, size, selected_quality)
        if not success:
            logger.warning(f"Primary download failed for {download_url}. Trying other qualities/mirrors as fallback...")
            fallback_urls = [url for q, url in qualities.items() if url != download_url]
            # Prioritize HLS/m3u8 mirrors
            fallback_urls.sort(key=lambda u: 0 if (".m3u8" in u or "wish" in u or "swdyu" in u) else 1)
            
            for fb_url in fallback_urls:
                logger.info(f"Trying fallback download mirror: {fb_url}")
                if temp_file_path.exists():
                    try: os.remove(temp_file_path)
                    except Exception: pass
                    
                if status_msg_id:
                    try:
                        await bot.edit_message_text("🔄 جاري محاولة التحميل من خادم بديل...", chat_id=chat_id, message_id=status_msg_id)
                    except Exception: pass
                
                from app.services.downloader import get_url_file_size
                async with aiohttp.ClientSession() as size_session:
                    fb_size = await get_url_file_size(fb_url, size_session)
                if fb_size <= 0:
                    fb_size = size
                    
                success = await download_file(fb_url, temp_file_path, proxy_msg, fb_size, selected_quality)
                if success:
                    logger.info(f"Fallback download succeeded using mirror: {fb_url}")
                    break
                    
        if not success:
            if status_msg_id:
                try: await bot.edit_message_text("❌ فشل تحميل الملف من كافة خوادم البث المتاحة.", chat_id=chat_id, message_id=status_msg_id)
                except Exception: pass
            return False

        # 5. FFmpeg Low-RAM Compression Safety Valve
        actual_size = os.path.getsize(temp_file_path)
        if actual_size > 1.95 * 1024 * 1024 * 1024:
            if status_msg_id:
                try: await bot.edit_message_text("⚙️ حجم الملف يتجاوز 2 جيجابايت. جاري ضغط الفيديو لتجنب عوائق تلغرام...", chat_id=chat_id, message_id=status_msg_id)
                except Exception: pass
            
            compressed_filename = f"compressed_{filename}"
            compressed_file_path = config.DOWNLOAD_DIR / compressed_filename
            
            # Acquire semaphore to serialize FFmpeg compression tasks (prevent RAM crash)
            async with ffmpeg_semaphore:
                try:
                    # ffmpeg -y -i input.mp4 -vcodec libx264 -crf 28 -preset ultrafast -threads 1 -acodec copy output.mp4
                    process = await asyncio.create_subprocess_exec(
                        "ffmpeg",
                        "-y",
                        "-i", str(temp_file_path),
                        "-vcodec", "libx264",
                        "-crf", "28",
                        "-preset", "ultrafast",
                        "-threads", "1",
                        "-acodec", "copy",
                        str(compressed_file_path),
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    stdout, stderr = await process.communicate()
                    if process.returncode == 0 and compressed_file_path.exists():
                        logger.info(f"Video compressed from {actual_size / (1024*1024):.1f} MB to {os.path.getsize(compressed_file_path) / (1024*1024):.1f} MB")
                        os.unlink(temp_file_path)
                        temp_file_path = compressed_file_path
                        size_mb = os.path.getsize(temp_file_path) / (1024 * 1024)
                    else:
                        raise Exception("FFmpeg compression process failed")
                except Exception as comp_e:
                    logger.warning(f"Failed to compress video: {comp_e}. Falling back to URL delivery.")
                    if compressed_file_path.exists():
                        try: os.unlink(compressed_file_path)
                        except Exception: pass
                    # Send direct link fallback as Plan B (NO raw HTTP text links shortcuts)
                    fallback_text = (
                        f"❌ حجم الملف هو `{actual_size / (1024*1024*1024):.2f} جيجابايت` وهو يتجاوز حد تلغرام الأقصى للرفع (2 جيجابايت).\n"
                        f"فشل خادم الضغط التلقائي."
                    )
                    if status_msg_id:
                        try: await bot.edit_message_text(fallback_text, chat_id=chat_id, message_id=status_msg_id, parse_mode="Markdown")
                        except Exception: pass
                    return False

        # 6. Upload/Send video to the user
        if status_msg_id:
            try: await bot.edit_message_text("📤 جاري رفع الفيديو إلى تلغرام...", chat_id=chat_id, message_id=status_msg_id)
            except Exception: pass

        video_file = FSInputFile(str(temp_file_path))
        thumb_input = await get_video_thumbnail(bot, db_session_factory, anilist_id)

        # Probe exact video metadata (duration, width, height) using ffprobe to force custom thumbnail display
        probe_duration, video_width, video_height = await get_video_metadata(temp_file_path)
        final_duration = probe_duration or parse_duration_to_seconds(duration_str)

        sent_msg = await bot.send_video(
            chat_id=chat_id,
            video=video_file,
            thumbnail=thumb_input,
            width=video_width,
            height=video_height,
            duration=final_duration,
            caption=caption,
            supports_streaming=True,
            reply_markup=nav_markup,
            parse_mode="HTML"
        )
        uploaded_file_id = sent_msg.video.file_id

        # Delete status message
        if status_msg_id:
            try: await bot.delete_message(chat_id=chat_id, message_id=status_msg_id)
            except Exception: pass

        # 7. Mirror to Library Group
        await mirror_video_to_library(bot, db_session_factory, anilist_id, anime_title, episode_num, selected_quality, uploaded_file_id)

        # 8. Cache uploaded Telegram file ID globally and strictly in TelegramFileCache DB
        await save_telegram_file_cache(db_session_factory, anilist_id, episode_num, selected_quality, uploaded_file_id, file_size_mb=size_mb)

        async with db_session_factory() as session:
            stmt_update = select(DownloadCache).where(DownloadCache.play_url == play_url)
            res_update = await session.execute(stmt_update)
            cached_update = res_update.scalar_one_or_none()
            if cached_update:
                updated_qualities = cached_update.qualities.copy()
                updated_qualities[selected_quality] = uploaded_file_id
                cached_update.qualities = updated_qualities
                session.add(cached_update)
                await session.commit()
                logger.info(f"Cached Telegram file ID for {play_url} [{selected_quality}]")

        return True
    except Exception as e:
        logger.exception("Error executing download/upload task")
        if status_msg_id:
            try:
                await bot.edit_message_text(
                    f"❌ فشل الرفع: {e}",
                    chat_id=chat_id,
                    message_id=status_msg_id,
                    parse_mode="Markdown"
                )
            except Exception: pass
        return False
    finally:
        if temp_file_path and temp_file_path.exists():
            try: os.unlink(temp_file_path)
            except Exception: pass

async def mirror_video_to_library(
    bot: Bot,
    db_session_factory,
    anilist_id: int,
    anime_title: str,
    episode_num: str,
    quality: str,
    file_id: str
):
    """Automatically mirrors the completed video to its designated forum thread."""
    try:
        # Check topic cache
        topic_id = None
        async with db_session_factory() as session:
            stmt = select(AnimeTopicCache).where(AnimeTopicCache.anilist_id == anilist_id)
            res = await session.execute(stmt)
            topic_entry = res.scalar_one_or_none()
            if topic_entry:
                topic_id = topic_entry.topic_id

        if not topic_id:
            # Create a new forum topic in the library group
            logger.info(f"Creating new forum topic for {anime_title} in group {config.LIBRARY_GROUP_ID}")
            try:
                topic_info = await bot.create_forum_topic(chat_id=config.LIBRARY_GROUP_ID, name=anime_title[:120])
                topic_id = topic_info.message_thread_id
                
                # Cache topic ID
                async with db_session_factory() as session:
                    new_topic = AnimeTopicCache(anilist_id=anilist_id, topic_id=topic_id)
                    session.add(new_topic)
                    await session.commit()
            except Exception as thread_e:
                logger.warning(f"Failed to create forum topic in library group: {thread_e}. Falling back to default posting.")
                topic_id = None

        # Mirror video directly to forum thread or library group
        hashtag_name = make_hashtag(anime_title)
        footer = (
            f"🎬 <b>#{hashtag_name}</b>\n"
            f"🎞️ <b>الحلقة:</b> {episode_num}\n"
            f"⚙️ <b>الجودة:</b> #جودة_{quality}\n\n"
            f"🍿 مشاهدة ممتعة!"
        )
        
        await bot.send_video(
            chat_id=config.LIBRARY_GROUP_ID,
            video=file_id,
            caption=footer,
            message_thread_id=topic_id,
            supports_streaming=True,
            parse_mode="HTML"
        )
        logger.info(f"Successfully mirrored {anime_title} ep {episode_num} to library thread {topic_id}")
    except Exception as mirror_e:
        logger.warning(f"Error mirroring video to library group: {mirror_e}")
