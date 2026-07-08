import html
import asyncio
import json
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, URLInputFile
from config import config
from app.utils.logging_config import logger
from app.utils.deeplink import encode_deeplink_payload
from app.utils.settings import get_setting, set_setting

DEFAULT_NOTIFICATION_GROUP_ID = "-1003876536923"

async def get_active_notification_group_id() -> str:
    """Retrieves the notification group/channel ID from DB settings or returns default fallback."""
    return await get_setting("notification_group_id", DEFAULT_NOTIFICATION_GROUP_ID)

async def broadcast_new_episode_notification(
    bot: Bot,
    anilist_id: int,
    anime_title: str,
    episode_num: str,
    image_url: Optional[str] = None,
    target_chat_id: Optional[str] = None
) -> bool:
    """Broadcasts a new episode notification card in 100% Arabic to the configured notification group."""
    chat_id = target_chat_id or await get_active_notification_group_id()
    if not chat_id or chat_id == "disabled":
        logger.info("Notification broadcasting is disabled or group ID is not set.")
        return False

    logger.info(f"Preparing 100% Arabic new episode notification for '{anime_title}' Ep {episode_num} to {chat_id}")
    
    try:
        bot_info = await bot.get_me()
        bot_username = bot_info.username if bot_info else "anime_wrbot"
        
        payload = encode_deeplink_payload(anilist_id, episode_num, anime_title=anime_title)
        deeplink_url = f"https://t.me/{bot_username}?start={payload}"
        
        chans = [c.strip() for c in (config.CHANNEL_USERNAME or "").replace(",", " ").split() if c.strip()]
        first_chan = chans[0] if chans else f"@{bot_username}"
        chan_url = f"https://t.me/{first_chan.lstrip('@')}"
        
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        caption_text = (
            f"🔥 <b>حلقة جديدة متوفرة الآن!</b>\n\n"
            f"🎬 <b>اسم الأنمي:</b> {html.escape(anime_title)}\n"
            f"🔢 <b>رقم الحلقة:</b> {episode_num}\n"
            f"📅 <b>تاريخ الإضافة:</b> {today_str}\n\n"
            f"👇 <b>للمشاهدة والتحميل المباشر عبر البوت:</b>"
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎥 مشاهدة الآن", url=deeplink_url)],
            [InlineKeyboardButton(text="📢 قناة البوت الرسمية", url=chan_url)]
        ])
        
        # Check for custom ads poster configured by the admin
        custom_poster = await get_setting("ads_poster_file_id")
        if custom_poster:
            photo = custom_poster
        else:
            # Fallback to a high-quality default anime poster if no image is available
            DEFAULT_POSTER_URL = "https://images.unsplash.com/photo-1578632767115-351597cf2477?w=600&auto=format&fit=crop"
            final_image = image_url if (image_url and image_url.startswith("http")) else DEFAULT_POSTER_URL
            photo = URLInputFile(final_image)
            
        await bot.send_photo(
            chat_id=chat_id,
            photo=photo,
            caption=caption_text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
            
        logger.info(f"Successfully sent 100% Arabic episode notification for {anime_title} Ep {episode_num}")
        return True
    except Exception as e:
        logger.exception(f"Failed to send new episode notification: {e}")
        return False


async def start_latest_episodes_notifier_loop(bot: Bot, db_session_factory):
    """Background loop that periodically checks the site for newly released episodes and sends automatic alerts with delay."""
    if not getattr(config, "ENABLE_LATEST_NOTIFIER", True):
        logger.info("Automatic latest episodes notifier is disabled via config settings.")
        return

    logger.info("Starting automatic latest episodes notifier background loop...")
    
    while True:
        try:
            from app.services.scraper import fetch_latest_site_episodes
            latest_episodes = await fetch_latest_site_episodes()
            
            if latest_episodes:
                raw_history = await get_setting("notified_episodes_history", None)
                
                # First run initialization: seed history with current site episodes and post the latest 5 as a test
                if raw_history is None:
                    initial_keys = [f"{ep['anime_title']}:{ep['episode_num']}" for ep in latest_episodes]
                    
                    # Post the latest 5 episodes on first startup (index 0 is newest, index 4 is fifth newest)
                    startup_demo_eps = latest_episodes[:5]
                    logger.info(f"First run: Broadcasting notifications for the newest 5 episodes (out of {len(latest_episodes)}) as a startup test.")
                    
                    for ep in reversed(startup_demo_eps):
                        anilist_id = 0
                        image_url = ep.get("poster_url")
                        try:
                            from app.services.anilist import search_anime_anilist
                            res = await search_anime_anilist(ep['anime_title'])
                            if res:
                                anilist_id = res[0]['anilist_id']
                                image_url = res[0].get('image_url') or image_url
                        except Exception:
                            pass
                            
                        await broadcast_new_episode_notification(
                            bot=bot,
                            anilist_id=anilist_id,
                            anime_title=ep['anime_title'],
                            episode_num=ep['episode_num'],
                            image_url=image_url
                        )
                        await asyncio.sleep(2)
                        
                    await set_setting("notified_episodes_history", json.dumps(initial_keys))
                    await set_setting("pending_notifications_queue", "{}")
                    logger.info(f"Seeded notification history with {len(initial_keys)} existing site episodes.")
                else:
                    try:
                        history = json.loads(raw_history)
                    except Exception:
                        history = []
                        
                    raw_pending = await get_setting("pending_notifications_queue", "{}")
                    try:
                        pending_queue = json.loads(raw_pending)
                    except Exception:
                        pending_queue = {}
                        
                    # 1. Add newly discovered episodes to the pending queue
                    queue_updated = False
                    for ep in reversed(latest_episodes):
                        ep_key = f"{ep['anime_title']}:{ep['episode_num']}"
                        if ep_key not in history and ep_key not in pending_queue:
                            logger.info(f"New released episode queued for delay: {ep_key}")
                            pending_queue[ep_key] = {
                                "anime_title": ep['anime_title'],
                                "episode_num": ep['episode_num'],
                                "poster_url": ep.get("poster_url"),
                                "discovered_at": datetime.now(timezone.utc).isoformat()
                            }
                            queue_updated = True
                            
                    if queue_updated:
                        await set_setting("pending_notifications_queue", json.dumps(pending_queue))
                        
                    # 2. Process pending queue and broadcast those that have passed the delay threshold
                    history_updated = False
                    keys_to_remove = []
                    
                    for ep_key, ep_data in list(pending_queue.items()):
                        try:
                            discovered_at = datetime.fromisoformat(ep_data["discovered_at"])
                            elapsed_seconds = (datetime.now(timezone.utc) - discovered_at).total_seconds()
                            delay_seconds = getattr(config, "NOTIFICATION_DELAY_MINUTES", 120) * 60
                            
                            if elapsed_seconds >= delay_seconds:
                                logger.info(f"Delay threshold reached for {ep_key} (elapsed: {int(elapsed_seconds)}s, target: {delay_seconds}s). Broadcasting...")
                                
                                # Try resolving AniList ID if possible
                                anilist_id = 0
                                image_url = ep_data.get("poster_url")
                                try:
                                    from app.services.anilist import search_anime_anilist
                                    res = await search_anime_anilist(ep_data['anime_title'])
                                    if res:
                                        anilist_id = res[0]['anilist_id']
                                        image_url = res[0].get('image_url') or image_url
                                except Exception:
                                    pass
                                    
                                success = await broadcast_new_episode_notification(
                                    bot=bot,
                                    anilist_id=anilist_id,
                                    anime_title=ep_data['anime_title'],
                                    episode_num=ep_data['episode_num'],
                                    image_url=image_url
                                )
                                
                                if success:
                                    history.append(ep_key)
                                    history_updated = True
                                    keys_to_remove.append(ep_key)
                                    await asyncio.sleep(3)  # Rate limiting between posts
                            else:
                                logger.info(f"Episode {ep_key} is still pending (elapsed: {int(elapsed_seconds)}s / {delay_seconds}s)")
                        except Exception as item_err:
                            logger.warning(f"Error processing pending notification item {ep_key}: {item_err}")
                            
                    # Remove sent notifications from the queue
                    if keys_to_remove:
                        for k in keys_to_remove:
                            if k in pending_queue:
                                del pending_queue[k]
                        await set_setting("pending_notifications_queue", json.dumps(pending_queue))
                        
                    if history_updated:
                        # Keep history capped at last 200 items
                        history = history[-200:]
                        await set_setting("notified_episodes_history", json.dumps(history))
        except Exception as e:
            logger.warning(f"Error in latest episodes notifier loop: {e}")
            
        # Wait 3 minutes before checking site again
        await asyncio.sleep(180)


async def get_database_backup_file(target_path) -> bool:
    """Generates a portable SQLite database file backup from active database (SQLite or PostgreSQL)."""
    from pathlib import Path
    import shutil
    from sqlalchemy import select, insert
    from sqlalchemy.ext.asyncio import create_async_engine
    from app.database.connection import AsyncSessionLocal
    from app.database.models import Base
    
    db_url = config.DATABASE_URL
    target_path = Path(target_path)
    
    if "postgresql" not in db_url:
        # SQLite backup: Copy database file directly
        db_file_name = "bot.db"
        if "sqlite" in db_url:
            db_file_name = db_url.split("///")[-1]
            
        project_root = Path(r"c:\Users\monsm\OneDrive\Desktop\BOT")
        db_path = Path(db_file_name)
        if not db_path.is_absolute():
            db_path = project_root / db_path
            
        if db_path.exists():
            shutil.copy2(db_path, target_path)
            return True
        return False
    else:
        # PostgreSQL backup: Dump all tables to local SQLite target_path dynamically
        try:
            if target_path.exists():
                target_path.unlink()
                
            temp_sqlite_url = f"sqlite+aiosqlite:///{target_path}"
            temp_engine = create_async_engine(temp_sqlite_url)
            
            async with temp_engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
                
            async with AsyncSessionLocal() as session:
                for mapper in Base.registry.mappers:
                    model_class = mapper.class_
                    columns = mapper.columns.keys()
                    
                    stmt = select(model_class)
                    res = await session.execute(stmt)
                    records = res.scalars().all()
                    
                    if records:
                        async with temp_engine.begin() as temp_conn:
                            for record in records:
                                data = {c: getattr(record, c) for c in columns}
                                await temp_conn.execute(insert(model_class).values(data))
                                
            await temp_engine.dispose()
            return True
        except Exception as e:
            logger.exception(f"Error copying database records to local SQLite: {e}")
            if target_path.exists():
                try: target_path.unlink()
                except Exception: pass
            return False


async def start_daily_database_backup_loop(bot: Bot):
    """Background loop that automatically sends database backups once every 24 hours to the Super Admin."""
    from pathlib import Path
    from aiogram.types import FSInputFile
    
    logger.info("Starting daily database backup loop...")
    while True:
        try:
            last_backup_str = await get_setting("last_db_backup_time", None)
            now = datetime.now(timezone.utc)
            
            should_backup = False
            if not last_backup_str:
                should_backup = True
            else:
                try:
                    last_backup = datetime.fromisoformat(last_backup_str)
                    elapsed = (now - last_backup).total_seconds()
                    # 24 hours = 86400 seconds
                    if elapsed >= 86400:
                        should_backup = True
                    else:
                        remaining = max(60, 86400 - elapsed)
                        logger.info(f"Daily database backup is not due yet. Remaining sleep time: {remaining:.1f} seconds")
                        await asyncio.sleep(remaining)
                        continue
                except Exception:
                    should_backup = True
                    
            if should_backup:
                temp_backup_path = config.DOWNLOAD_DIR / "daily_backup.db"
                success = await get_database_backup_file(temp_backup_path)
                
                if success and temp_backup_path.exists():
                    logger.info(f"Sending automated daily database backup to Super Admin ({config.SUPER_ADMIN_ID})...")
                    db_doc = FSInputFile(str(temp_backup_path), filename="bot_backup.db")
                    await bot.send_document(
                        chat_id=config.SUPER_ADMIN_ID,
                        document=db_doc,
                        caption=f"🤖 <b>نسخة احتياطية تلقائية لقاعدة البيانات (Daily Backup)</b>\n\n📅 التاريخ: <code>{now.strftime('%Y-%m-%d %H:%M:%S')} UTC</code>"
                    )
                    await set_setting("last_db_backup_time", now.isoformat())
                    logger.info("Daily database backup successfully sent.")
                    try: temp_backup_path.unlink()
                    except Exception: pass
                else:
                    logger.warning("Could not generate database backup file.")
        except Exception as e:
            logger.warning(f"Error in daily database backup loop: {e}")
            
        await asyncio.sleep(3600)
