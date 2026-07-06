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
        
        payload = encode_deeplink_payload(anilist_id, episode_num)
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
        
        if image_url and image_url.startswith("http"):
            photo = URLInputFile(image_url)
            await bot.send_photo(
                chat_id=chat_id,
                photo=photo,
                caption=caption_text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
        else:
            await bot.send_message(
                chat_id=chat_id,
                text=caption_text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            
        logger.info(f"Successfully sent 100% Arabic episode notification for {anime_title} Ep {episode_num}")
        return True
    except Exception as e:
        logger.exception(f"Failed to send new episode notification: {e}")
        return False


async def start_latest_episodes_notifier_loop(bot: Bot, db_session_factory):
    """Background loop that periodically checks the site for newly released episodes and sends automatic alerts."""
    logger.info("Starting automatic latest episodes notifier background loop...")
    
    while True:
        try:
            from app.services.scraper import fetch_latest_site_episodes
            latest_episodes = await fetch_latest_site_episodes()
            
            if latest_episodes:
                raw_history = await get_setting("notified_episodes_history", None)
                
                # First run initialization: seed history with current site episodes to avoid notification spam on startup
                if raw_history is None:
                    initial_keys = [f"{ep['anime_title']}:{ep['episode_num']}" for ep in latest_episodes]
                    await set_setting("notified_episodes_history", json.dumps(initial_keys))
                    logger.info(f"Seeded notification history with {len(initial_keys)} existing site episodes.")
                else:
                    try:
                        history = json.loads(raw_history)
                    except Exception:
                        history = []
                        
                    updated = False
                    for ep in reversed(latest_episodes):
                        ep_key = f"{ep['anime_title']}:{ep['episode_num']}"
                        if ep_key not in history:
                            logger.info(f"New released episode detected on site: {ep_key}")
                            
                            # Try resolving AniList ID if possible
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
                                
                            success = await broadcast_new_episode_notification(
                                bot=bot,
                                anilist_id=anilist_id,
                                anime_title=ep['anime_title'],
                                episode_num=ep['episode_num'],
                                image_url=image_url
                            )
                            
                            if success:
                                history.append(ep_key)
                                updated = True
                                await asyncio.sleep(3)  # Rate limiting between posts
                                
                    if updated:
                        # Keep history capped at last 200 items
                        history = history[-200:]
                        await set_setting("notified_episodes_history", json.dumps(history))
        except Exception as e:
            logger.warning(f"Error in latest episodes notifier loop: {e}")
            
        # Wait 3 minutes before checking site again
        await asyncio.sleep(180)
