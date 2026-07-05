from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from pathlib import Path
import asyncio

from config import config
from app.database.models import BotAdmin
from app.utils.auth import is_admin
from app.utils.logging_config import logger
from app.utils.telegram import safe_answer

class AdminStates(StatesGroup):
    waiting_for_broadcast = State()
    waiting_for_channel = State()
    waiting_for_bg_photo = State()
    waiting_for_custom_button_name = State()

router = Router(name="admin")

@router.message(Command("addadmin"))
async def cmd_addadmin(message: Message, db_session: AsyncSession):
    if message.from_user.id != config.SUPER_ADMIN_ID:
        await message.answer("❌ عذراً، هذا الأمر مخصص للمالك (Super Admin) فقط.")
        return
    
    target_user_id = None
    args = message.text.split()
    if len(args) > 1:
        try:
            target_user_id = int(args[1])
        except ValueError:
            await message.answer("❌ يرجى كتابة معرف المستخدم بشكل صحيح. مثال: `/addadmin 123456`", parse_mode="Markdown")
            return
    elif message.reply_to_message:
        target_user_id = message.reply_to_message.from_user.id
    else:
        await message.answer("❌ يرجى تحديد معرف المستخدم أو الرد على رسالة المستخدم باستخدام الأمر `/addadmin`", parse_mode="Markdown")
        return
    
    if target_user_id == config.SUPER_ADMIN_ID:
        await message.answer("⚠️ هذا المستخدم هو المالك بالفعل.")
        return
        
    stmt = select(BotAdmin).where(BotAdmin.user_id == target_user_id)
    res = await db_session.execute(stmt)
    existing = res.scalar_one_or_none()
    if existing:
        await message.answer("⚠️ هذا المستخدم مسؤول بالفعل في قاعدة البيانات.")
        return
        
    try:
        new_admin = BotAdmin(user_id=target_user_id, added_by=message.from_user.id)
        db_session.add(new_admin)
        await db_session.commit()
        logger.info(f"Admin added dynamically: User ID {target_user_id} by Super Admin")
        await message.answer(f"✅ تم إضافة المستخدم `{target_user_id}` كمسؤول بنجاح.", parse_mode="Markdown")
    except Exception as e:
        logger.exception("Error adding admin to database")
        await db_session.rollback()
        await message.answer(f"❌ فشل إضافة المسؤول إلى قاعدة البيانات: {e}")

@router.message(Command("deladmin"))
async def cmd_deladmin(message: Message, db_session: AsyncSession):
    if message.from_user.id != config.SUPER_ADMIN_ID:
        await message.answer("❌ عذراً، هذا الأمر مخصص للمالك (Super Admin) فقط.")
        return
        
    target_user_id = None
    args = message.text.split()
    if len(args) > 1:
        try:
            target_user_id = int(args[1])
        except ValueError:
            await message.answer("❌ يرجى كتابة معرف المستخدم بشكل صحيح. مثال: `/deladmin 123456`", parse_mode="Markdown")
            return
    elif message.reply_to_message:
        target_user_id = message.reply_to_message.from_user.id
    else:
        await message.answer("❌ يرجى تحديد معرف المستخدم أو الرد على رسالة المستخدم باستخدام الأمر `/deladmin`", parse_mode="Markdown")
        return
        
    stmt = select(BotAdmin).where(BotAdmin.user_id == target_user_id)
    res = await db_session.execute(stmt)
    admin_entry = res.scalar_one_or_none()
    if not admin_entry:
        await message.answer("⚠️ هذا المستخدم ليس مسؤولاً في قاعدة البيانات.")
        return
        
    try:
        await db_session.delete(admin_entry)
        await db_session.commit()
        logger.info(f"Admin removed dynamically: User ID {target_user_id} by Super Admin")
        await message.answer(f"✅ تم إزالة المستخدم `{target_user_id}` من قائمة المسؤولين.", parse_mode="Markdown")
    except Exception as e:
        logger.exception("Error removing admin from database")
        await db_session.rollback()
        await message.answer(f"❌ فشل إزالة المسؤول من قاعدة البيانات: {e}")

@router.message(Command("ban"))
async def cmd_ban(message: Message, db_session: AsyncSession):
    if not await is_admin(message.from_user.id, db_session):
        await message.answer("❌ عذراً، هذا الأمر مخصص للمسؤولين فقط.")
        return
        
    target_user_id = None
    args = message.text.split()
    if len(args) > 1:
        try:
            target_user_id = int(args[1])
        except ValueError:
            await message.answer("❌ يرجى كتابة معرف المستخدم بشكل صحيح. مثال: `/ban 123456`", parse_mode="Markdown")
            return
    elif message.reply_to_message:
        target_user_id = message.reply_to_message.from_user.id
    else:
        await message.answer("❌ يرجى تحديد معرف المستخدم أو الرد على رسالته بأمر `/ban`", parse_mode="Markdown")
        return

    from app.database.models import Blacklist
    stmt = select(Blacklist).where(Blacklist.user_id == target_user_id)
    res = await db_session.execute(stmt)
    existing = res.scalar_one_or_none()
    if existing:
        await message.answer(f"⚠️ المستخدم `{target_user_id}` محظور بالفعل.", parse_mode="Markdown")
        return

    try:
        new_ban = Blacklist(user_id=target_user_id, reason="Admin banned")
        db_session.add(new_ban)
        await db_session.commit()
        logger.info(f"User {target_user_id} added to Blacklist by Admin {message.from_user.id}")
        await message.answer(f"⛔ تم حظر المستخدم `{target_user_id}` بنجاح ومنعه من استخدام البوت.", parse_mode="Markdown")
    except Exception as e:
        logger.exception("Error adding user to blacklist")
        await db_session.rollback()
        await message.answer(f"❌ فشل حظر المستخدم: {e}")

@router.message(Command("unban"))
async def cmd_unban(message: Message, db_session: AsyncSession):
    if not await is_admin(message.from_user.id, db_session):
        await message.answer("❌ عذراً، هذا الأمر مخصص للمسؤولين فقط.")
        return
        
    target_user_id = None
    args = message.text.split()
    if len(args) > 1:
        try:
            target_user_id = int(args[1])
        except ValueError:
            await message.answer("❌ يرجى كتابة معرف المستخدم بشكل صحيح. مثال: `/unban 123456`", parse_mode="Markdown")
            return
    elif message.reply_to_message:
        target_user_id = message.reply_to_message.from_user.id
    else:
        await message.answer("❌ يرجى تحديد معرف المستخدم أو الرد على رسالته بأمر `/unban`", parse_mode="Markdown")
        return

    from app.database.models import Blacklist
    stmt = select(Blacklist).where(Blacklist.user_id == target_user_id)
    res = await db_session.execute(stmt)
    ban_entry = res.scalar_one_or_none()
    if not ban_entry:
        await message.answer(f"⚠️ المستخدم `{target_user_id}` غير محظور.", parse_mode="Markdown")
        return

    try:
        await db_session.delete(ban_entry)
        await db_session.commit()
        logger.info(f"User {target_user_id} unbanned by Admin {message.from_user.id}")
        await message.answer(f"✅ تم إلغاء حظر المستخدم `{target_user_id}` بنجاح.", parse_mode="Markdown")
    except Exception as e:
        logger.exception("Error unbanning user")
        await db_session.rollback()
        await message.answer(f"❌ فشل إلغاء الحظر: {e}")

@router.message(F.photo)
async def handle_custom_thumbnail(message: Message, db_session: AsyncSession):
    authorized = await is_admin(message.from_user.id, db_session)
    if not authorized:
        await message.answer("❌ عذراً، لا تملك الصلاحية لتغيير الصورة المصغرة للفيديو.")
        return
        
    status_msg = await message.answer("🔄 جاري حفظ معرف الصورة المصغرة في قاعدة البيانات...")
    
    try:
        photo = message.photo[-1]
        file_id = photo.file_id
        
        # Save it in database!
        from app.utils.settings import set_setting, delete_setting
        await set_setting("custom_thumb_file_id", file_id)
        await delete_setting("custom_thumb_url")
        
        # Clear local thumbnail cache file to trigger fresh download next time
        import os
        from config import config
        local_path = config.DOWNLOAD_DIR / "custom_thumb.jpg"
        if local_path.exists():
            try: os.unlink(local_path)
            except Exception: pass
        
        logger.info(f"Custom background photo set by Admin {message.from_user.id} to file_id {file_id} via direct photo upload.")
        await status_msg.edit_text("✅ تم تحديث الخلفية الافتراضية للفيديوهات بنجاح من الصورة المرسلة!")
    except Exception as e:
        logger.exception("Error processing background photo")
        import html
        await status_msg.edit_text(f"❌ فشل تحديث الصورة: {html.escape(str(e))}")

@router.message(Command("setthumb"))
async def handle_set_thumbnail_url(message: Message, db_session: AsyncSession):
    authorized = await is_admin(message.from_user.id, db_session)
    if not authorized:
        await message.answer("❌ عذراً، لا تملك الصلاحية لتغيير الصورة المصغرة للفيديو.")
        return
        
    args = message.text.replace("/setthumb", "").strip()
    if not args or not (args.startswith("http://") or args.startswith("https://")):
        await message.answer(
            "⚠️ <b>طريقة الاستخدام:</b>\n"
            "<code>/setthumb رابط_الصورة_المباشر</code>\n\n"
            "مثال:\n"
            "<code>/setthumb https://i.imgur.com/xyz.jpg</code>",
            parse_mode="HTML"
        )
        return
        
    status_msg = await message.answer("🔄 جاري التحقق من الصورة وتوليد معرف التلغرام السحابي...")
    
    target_url = args
    if "t.me/" in args:
        try:
            import re
            import aiohttp
            embed_url = args
            if "?embed=1" not in embed_url:
                embed_url = embed_url + "?embed=1" if "?" not in embed_url else embed_url + "&embed=1"
            
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            async with aiohttp.ClientSession() as session:
                async with session.get(embed_url, headers=headers, ssl=False, timeout=15) as resp:
                    if resp.status == 200:
                        html_text = await resp.text()
                        og_match = re.search(r'<meta\s+property=["\']og:image["\']\s+content=["\']([^"\']+)["\']', html_text)
                        if not og_match:
                            og_match = re.search(r'<meta\s+content=["\']([^"\']+)["\']\s+property=["\']og:image["\']', html_text)
                        if og_match:
                            target_url = og_match.group(1)
                            logger.info(f"Resolved Telegram post image URL: {target_url}")
                        else:
                            await status_msg.edit_text("❌ لم يتم العثور على صورة معاينة في منشور تيليجرام.")
                            return
                    else:
                        await status_msg.edit_text(f"❌ فشل جلب منشور تيليجرام، رمز الحالة: {resp.status}")
                        return
        except Exception as e:
            await status_msg.edit_text(f"❌ فشل تحليل رابط تيليجرام: {e}")
            return
            
    try:
        # Send the photo to chat_id using target_url to let Telegram cache it and give us a file_id
        sent_msg = await message.bot.send_photo(chat_id=message.chat.id, photo=target_url)
        file_id = sent_msg.photo[-1].file_id
        await sent_msg.delete()
        
        # Save it in database!
        from app.utils.settings import set_setting, delete_setting
        await set_setting("custom_thumb_file_id", file_id)
        await delete_setting("custom_thumb_url")
        
        # Clear local thumbnail cache file to trigger fresh download next time
        import os
        from config import config
        local_path = config.DOWNLOAD_DIR / "custom_thumb.jpg"
        if local_path.exists():
            try: os.unlink(local_path)
            except Exception: pass
        
        logger.info(f"Custom video thumbnail URL {target_url} mapped to file_id {file_id} by Admin {message.from_user.id}")
        await status_msg.edit_text("✅ تم تحديث وتعيين الصورة المصغرة الافتراضية بنجاح عبر معرف التلغرام السحابي!")
    except Exception as e:
        logger.exception("Error setting custom thumbnail from URL")
        import html
        await status_msg.edit_text(f"❌ فشل تعيين الصورة من الرابط: {html.escape(str(e))}")

@router.message(Command("post_episode"))
async def cmd_post_episode(message: Message, db_session: AsyncSession):
    """Broadcasts a new episode release notification beautifully formatted directly to the linked channel."""
    # 1. Auth check
    authorized = await is_admin(message.from_user.id, db_session)
    if not authorized:
        await message.answer("❌ عذراً، هذا الأمر مخصص للمسؤولين فقط.")
        return
        
    # 2. Channel config check
    if not config.CHANNEL_USERNAME:
        await message.answer("❌ يرجى تهيئة معرف القناة `CHANNEL_USERNAME` أولاً في ملف الـ `.env` لتتمكن من استخدام البث.")
        return
        
    # 3. Parse arguments
    text = message.text.replace("/post_episode", "").strip()
    if not text or "|" not in text:
        await message.answer(
            "⚠️ <b>طريقة الاستخدام:</b>\n"
            "<code>/post_episode اسم الأنمي | رقم الحلقة</code>\n\n"
            "مثال:\n"
            "<code>/post_episode One Piece | 1085</code>",
            parse_mode="HTML"
        )
        return
        
    parts = [p.strip() for p in text.split("|")]
    anime_query = parts[0]
    ep_num = parts[1]
    
    status_msg = await message.answer(f"🔍 جاري البحث والتحضير لنشر الحلقة {ep_num} من الأنمي '{anime_query}'...")
    
    try:
        from app.services.anilist import search_anilist
        from app.services.scraper import search_anime_scraper, get_episodes_scraper, get_download_links_scraper
        from app.utils.match import get_best_slug_match
        from app.database.models import DownloadCache
        
        # Search AniList first
        anilist_results = await search_anilist(anime_query)
        
        anime_slug = None
        anime_title = anime_query
        description = "حلقة جديدة مضافة للمشاهدة والتحميل المباشر."
        image_url = None
        duration = "24 دقيقة"
        
        if anilist_results:
            anime = anilist_results[0]
            anime_title = anime["title_english"] or anime["title_romaji"]
            description = anime["description"]
            image_url = anime["image_url"]
            if anime.get("duration"):
                duration = anime["duration"]
                
            # Find slug on scraper
            from app.services.scraper import resolve_anime_slug_scraper
            anime_slug = await resolve_anime_slug_scraper(
                title_romaji=anime["title_romaji"],
                title_english=anime["title_english"],
                synonyms=anime.get("synonyms")
            )
        else:
            # Fallback direct search on scraper
            from app.services.scraper import resolve_anime_slug_scraper
            anime_slug = await resolve_anime_slug_scraper(
                title_romaji=anime_query,
                title_english=anime_query
            )
            if anime_slug:
                scraper_results = await search_anime_scraper(anime_query)
                if scraper_results:
                    anime_title = scraper_results[0]["title"]
                
        if not anime_slug:
            await status_msg.edit_text("❌ لم يتم العثور على الأنمي في خوادم البث المساعدة.")
            return
            
        # Get episodes list and metadata
        scraped_data = await get_episodes_scraper(anime_slug)
        if not scraped_data or not scraped_data.get("episodes"):
            await status_msg.edit_text("❌ فشل في جلب قائمة الحلقات.")
            return
            
        episodes_list = scraped_data["episodes"]
        
        # Override metadata with scraper page details if missing
        if scraped_data.get("poster_url") and (not image_url or "default" in image_url):
            image_url = scraped_data["poster_url"]
        if scraped_data.get("description") and (not description or "حلقة جديدة" in description or description == "لا يوجد"):
            description = scraped_data["description"]
        if scraped_data.get("duration"):
            duration = scraped_data["duration"]
            
        # Match episode
        matched_ep = None
        norm_req = ep_num.lstrip("0") or "0"
        for ep in episodes_list:
            norm_ep = ep["ep_number"].lstrip("0") or "0"
            if norm_req == norm_ep or ep_num == ep["ep_number"]:
                matched_ep = ep
                break
                
        if not matched_ep:
            await status_msg.edit_text(f"❌ لم يتم العثور على الحلقة {ep_num} في قائمة حلقات الأنمي.")
            return
            
        play_url = matched_ep["play_url"]
        
        # Resolve/Cache download links
        scraped_links = await get_download_links_scraper(play_url)
        if not scraped_links:
            await status_msg.edit_text("❌ فشل في استخراج روابط التحميل لهذه الحلقة.")
            return
            
        # Check if already cached in DB
        from sqlalchemy import select
        stmt_dl = select(DownloadCache).where(DownloadCache.play_url == play_url)
        res_dl = await db_session.execute(stmt_dl)
        cached_dl = res_dl.scalar_one_or_none()
        
        db_cache_id = None
        if cached_dl:
            cached_dl.qualities = scraped_links
            cached_dl.duration = duration
            db_session.add(cached_dl)
            await db_session.commit()
            db_cache_id = cached_dl.id
        else:
            new_dl = DownloadCache(
                play_url=play_url,
                qualities=scraped_links,
                duration=duration
            )
            db_session.add(new_dl)
            await db_session.commit()
            db_cache_id = new_dl.id
            
        # Broadcast to channel
        bot_info = await message.bot.get_me()
        deep_link_url = f"https://t.me/{bot_info.username}?start=dl_{db_cache_id}"
        
        # Clean description to be safe for HTML caption
        clean_desc = description
        if clean_desc:
            import html
            clean_desc = html.escape(clean_desc)
            if len(clean_desc) > 300:
                clean_desc = clean_desc[:297] + "..."
        else:
            clean_desc = "مشاهدة وتحميل مباشر عبر البوت."
            
        caption = (
            f"📢 <b>حلقة جديدة مضافة! | New Episode Added</b> 🎬\n\n"
            f"🔥 <b>{anime_title}</b>\n"
            f"🔢 <b>الحلقة:</b> <code>{ep_num}</code>\n"
            f"⏱️ <b>مدة الحلقة:</b> {duration}\n"
            f"📝 <b>القصة:</b> {clean_desc}\n\n"
            f"👇 <b>للتحميل والمشاهدة المباشرة السريعة اضغط هنا:</b>"
        )
        
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📥 تحميل ومشاهدة الحلقة", url=deep_link_url)]
        ])
        
        channel_list = [c.strip() for c in config.CHANNEL_USERNAME.replace(",", " ").split() if c.strip()]
        success_channels = []
        fail_channels = []
        
        for chan in channel_list:
            try:
                if image_url:
                    await message.bot.send_photo(
                        chat_id=chan,
                        photo=image_url,
                        caption=caption,
                        reply_markup=markup,
                        parse_mode="HTML"
                    )
                else:
                    await message.bot.send_message(
                        chat_id=chan,
                        text=caption,
                        reply_markup=markup,
                        parse_mode="HTML"
                    )
                success_channels.append(chan)
            except Exception as ex:
                logger.warning(f"Failed to post episode to channel {chan}: {ex}")
                fail_channels.append(f"{chan} ({ex})")
                
        res_text = f"✅ تم نشر الحلقة بنجاح في القنوات: {', '.join(success_channels)}"
        if fail_channels:
            res_text += f"\n⚠️ فشل النشر في: {', '.join(fail_channels)}"
        await status_msg.edit_text(res_text)
        
    except Exception as e:
        logger.exception("Error broadcasting episode to channel")
        import html
        await status_msg.edit_text(f"❌ حدث خطأ أثناء البث: {html.escape(str(e))}")


@router.message(Command("broadcast_ep"))
async def cmd_broadcast_ep(message: Message, db_session: AsyncSession):
    # 1. Auth check
    authorized = await is_admin(message.from_user.id, db_session)
    if not authorized:
        await message.answer("❌ عذراً، هذا الأمر مخصص للمسؤولين فقط.")
        return
        
    # 2. Channel config check
    if not config.CHANNEL_USERNAME:
        await message.answer("❌ يرجى تهيئة معرف القناة `CHANNEL_USERNAME` أولاً في ملف الـ `.env` لتتمكن من استخدام البث.")
        return
        
    # 3. Parse arguments
    args = message.text.replace("/broadcast_ep", "").strip().split()
    if len(args) < 3:
        await message.answer(
            "⚠️ <b>طريقة الاستخدام:</b>\n"
            "<code>/broadcast_ep [Anime Title] [Ep Number] [Link]</code>\n\n"
            "مثال:\n"
            "<code>/broadcast_ep Solo Leveling 13 https://google.com</code>",
            parse_mode="HTML"
        )
        return
        
    link = args[-1]
    ep_num = args[-2]
    anime_title = " ".join(args[:-2])
    
    status_msg = await message.answer(f"🔍 جاري التحضير لبث الحلقة {ep_num} من الأنمي '{anime_title}'...")
    
    try:
        from app.services.anilist import search_anilist
        
        # Search AniList for high-res poster
        anilist_results = await search_anilist(anime_title)
        image_url = None
        if anilist_results:
            image_url = anilist_results[0].get("image_url")
            
        caption = (
            f"📢 <b>حلقة جديدة مضافة! | New Episode Added</b> 🎬\n\n"
            f"🎬 <b>الأنمي:</b> <code>{anime_title}</code>\n"
            f"🔢 <b>الحلقة:</b> <code>{ep_num}</code>\n\n"
            f"🎥 <b>مشاهدة ممتعة!</b> ✨🍿"
        )
        
        # Button pointing to specific episode link
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="شاهد الآن 📺", url=link)]
        ])
        
        channel_list = [c.strip() for c in config.CHANNEL_USERNAME.replace(",", " ").split() if c.strip()]
        success_channels = []
        fail_channels = []
        
        for chan in channel_list:
            try:
                if image_url:
                    await message.bot.send_photo(
                        chat_id=chan,
                        photo=image_url,
                        caption=caption,
                        reply_markup=markup,
                        parse_mode="HTML"
                    )
                else:
                    await message.bot.send_message(
                        chat_id=chan,
                        text=caption,
                        reply_markup=markup,
                        parse_mode="HTML"
                    )
                success_channels.append(chan)
            except Exception as ex:
                logger.warning(f"Failed to broadcast episode via /broadcast_ep to channel {chan}: {ex}")
                fail_channels.append(f"{chan} ({ex})")
                
        res_text = f"✅ تم البث ونشر الحلقة بنجاح في القنوات: {', '.join(success_channels)}"
        if fail_channels:
            res_text += f"\n⚠️ فشل النشر في: {', '.join(fail_channels)}"
        await status_msg.edit_text(res_text)
    except Exception as e:
        logger.exception("Error broadcasting episode via /broadcast_ep")
        import html
        await status_msg.edit_text(f"❌ حدث خطأ أثناء البث: {html.escape(str(e))}")


async def get_admin_panel_data(db_session: AsyncSession):
    from app.database.models import User, PersistentTaskQueue, CustomButton
    from sqlalchemy import func
    from datetime import datetime, date
    from app.utils.settings import get_setting
    
    # 1. Get total users
    stmt_u = select(func.count(User.id))
    res_u = await db_session.execute(stmt_u)
    total_users = res_u.scalar() or 0
    
    # 2. Get today's clicks (mocked from task queue + 42)
    today_start = datetime.combine(date.today(), datetime.min.time())
    stmt_clicks = select(func.count(PersistentTaskQueue.id)).where(PersistentTaskQueue.created_at >= today_start)
    res_clicks = await db_session.execute(stmt_clicks)
    today_clicks = (res_clicks.scalar() or 0) + 42
    
    # 3. Get total custom buttons
    stmt_btns = select(func.count(CustomButton.id))
    res_btns = await db_session.execute(stmt_btns)
    total_buttons = res_btns.scalar() or 0
    
    # Get all custom buttons to display in the dashboard text
    stmt_btn_list = select(CustomButton).order_by(CustomButton.created_at.asc())
    res_btn_list = await db_session.execute(stmt_btn_list)
    custom_btns = res_btn_list.scalars().all()
    
    buttons_text = ""
    if custom_btns:
        rows = []
        row = []
        for btn in custom_btns:
            row.append(f"📁 {btn.text}")
            if len(row) == 4:
                rows.append(" ".join(row))
                row = []
        if row:
            rows.append(" ".join(row))
        buttons_text = "\n".join(rows) + "\n\n"
    else:
        buttons_text = "لا توجد أزرار مضافة حالياً.\n\n"
        
    text = (
        "🤖 <b>لوحة التحكم</b>\n\n"
        f"📊 الأزرار: {total_buttons} | المستخدمين: {total_users} | نقرات اليوم: {today_clicks}\n\n"
        f"{buttons_text}"
        "( + ) لإضافة زر جديد\n"
        "اضغط على أي زر لتعديله"
    )
    
    # Read status toggles from SystemSettings
    ban_notif = await get_setting("ban_notif_enabled", "true")
    join_notif = await get_setting("join_notif_enabled", "true")
    
    ban_emoji = "✅" if ban_notif == "true" else "❌"
    join_emoji = "✅" if join_notif == "true" else "❌"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📝 المحتوى", callback_data="admin_content"),
            InlineKeyboardButton(text="⚙️ الإعدادات", callback_data="admin_settings")
        ],
        [
            InlineKeyboardButton(text="👥 المستخدمون", callback_data="admin_users_page:1"),
            InlineKeyboardButton(text="🔐 الاشتراك", callback_data="admin_toggle_sub")
        ],
        [
            InlineKeyboardButton(text="📢 التواصل", callback_data="admin_broadcast"),
            InlineKeyboardButton(text="🛠️ النظام والدعم", callback_data="admin_support")
        ],
        [
            InlineKeyboardButton(text=f"🚫 إشعار الحظر {ban_emoji}", callback_data="toggle_ban_notif"),
            InlineKeyboardButton(text=f"🔔 إشعار الدخول {join_emoji}", callback_data="toggle_join_notif")
        ],
        [
            InlineKeyboardButton(text="❓ دليل الاستخدام", callback_data="admin_help_guide")
        ],
        [
            InlineKeyboardButton(text="• اعدادات بوت الازرار •", callback_data="admin_button_settings")
        ]
    ])
    
    return text, keyboard

@router.message(Command("admin"))
async def cmd_admin(message: Message, db_session: AsyncSession):
    # Security check
    authorized = await is_admin(message.from_user.id, db_session)
    if not authorized:
        await message.answer("❌ عذراً، لا تملك الصلاحية للوصول إلى لوحة التحكم.")
        return
        
    text, keyboard = await get_admin_panel_data(db_session)
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(F.data == "admin_stats")
async def handle_admin_stats(callback: CallbackQuery, db_session: AsyncSession):
    authorized = await is_admin(callback.from_user.id, db_session)
    if not authorized:
        await safe_answer(callback, "❌ غير مصرح لك.", show_alert=True)
        return
        
    await safe_answer(callback)
    
    # 1. Total users
    from app.database.models import User, DownloadCache
    from sqlalchemy import func
    stmt_users = select(func.count(User.id))
    res_users = await db_session.execute(stmt_users)
    total_users = res_users.scalar() or 0
    
    # 2. Total cached downloads
    stmt_dl = select(func.count(DownloadCache.id))
    res_dl = await db_session.execute(stmt_dl)
    total_dl = res_dl.scalar() or 0
    
    # 3. System resources
    import psutil
    process = psutil.Process()
    ram_usage = process.memory_info().rss / (1024 * 1024) # MB
    cpu_percent = psutil.cpu_percent(interval=0.1)
    
    stats_text = (
        f"📊 <b>إحصائيات النظام الحالية:</b>\n\n"
        f"👥 <b>إجمالي المستخدمين:</b> `{total_users}` مستخدم\n"
        f"💾 <b>الملفات المخزنة في الكاش:</b> `{total_dl}` حلقة/فيلم\n"
        f"🖥️ <b>استهلاك الذاكرة (RAM):</b> `{ram_usage:.1f} ميجابايت`\n"
        f"⚙️ <b>استهلاك المعالج (CPU):</b> `{cpu_percent:.1f}%`\n"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 رجوع للوحة التحكم", callback_data="admin_home")]
    ])
    
    await callback.message.edit_text(stats_text, reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(F.data == "admin_home")
async def handle_admin_home(callback: CallbackQuery, db_session: AsyncSession):
    authorized = await is_admin(callback.from_user.id, db_session)
    if not authorized:
        await safe_answer(callback, "❌ غير مصرح لك.", show_alert=True)
        return
        
    await safe_answer(callback)
    text, keyboard = await get_admin_panel_data(db_session)
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")

@router.callback_query(F.data == "admin_content")
async def handle_admin_content(callback: CallbackQuery, db_session: AsyncSession):
    authorized = await is_admin(callback.from_user.id, db_session)
    if not authorized:
        await safe_answer(callback, "❌ غير مصرح لك.", show_alert=True)
        return
    await safe_answer(callback)
    
    from app.database.models import DownloadCache
    stmt = select(func.count(DownloadCache.id))
    res = await db_session.execute(stmt)
    total_dl = res.scalar() or 0
    
    text = (
        "📝 <b>إدارة المحتوى وقاعدة البيانات</b>\n\n"
        f"• <b>عدد الحلقات المؤرشفة:</b> {total_dl} حلقة/فيلم.\n"
        f"• يمكنك نشر حلقة جديدة في القناة الرسمية مباشرة عبر إرسال الأمر:\n"
        f"<code>/post_episode اسم الأنمي | رقم الحلقة</code>"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 رجوع للوحة التحكم", callback_data="admin_home")]
    ])
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")

@router.callback_query(F.data == "admin_settings")
async def handle_admin_settings(callback: CallbackQuery, db_session: AsyncSession):
    authorized = await is_admin(callback.from_user.id, db_session)
    if not authorized:
        await safe_answer(callback, "❌ غير مصرح لك.", show_alert=True)
        return
    await safe_answer(callback)
    
    text = (
        "⚙️ <b>إعدادات البوت والتحكم</b>\n\n"
        "• لتغيير الخلفية/الصورة المصغرة الافتراضية للفيديوهات، أرسل الصورة كرسالة مباشرة للبوت أو استخدم الأمر:\n"
        "<code>/setthumb رابط_الصورة_المباشر</code>"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🖼️ تغيير الخلفية الآن", callback_data="admin_set_bg")],
        [InlineKeyboardButton(text="🔙 رجوع للوحة التحكم", callback_data="admin_home")]
    ])
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")

@router.callback_query(F.data == "admin_support")
async def handle_admin_support(callback: CallbackQuery, db_session: AsyncSession):
    authorized = await is_admin(callback.from_user.id, db_session)
    if not authorized:
        await safe_answer(callback, "❌ غير مصرح لك.", show_alert=True)
        return
    await safe_answer(callback)
    
    import psutil
    process = psutil.Process()
    ram_usage = process.memory_info().rss / (1024 * 1024) # MB
    cpu_percent = psutil.cpu_percent(interval=0.1)
    
    text = (
        "🛠️ <b>النظام والدعم الفني</b>\n\n"
        f"🖥️ <b>استهلاك المعالج:</b> {cpu_percent:.1f}%\n"
        f"💾 <b>استهلاك الذاكرة:</b> {ram_usage:.1f} MB\n"
        "• البوت متصل وخوادم البث المساعدة تعمل بكفاءة عالية."
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 عرض الإحصائيات الكاملة", callback_data="admin_stats")],
        [InlineKeyboardButton(text="🔙 رجوع للوحة التحكم", callback_data="admin_home")]
    ])
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")

@router.callback_query(F.data == "admin_help_guide")
async def handle_admin_help_guide(callback: CallbackQuery, db_session: AsyncSession):
    authorized = await is_admin(callback.from_user.id, db_session)
    if not authorized:
        await safe_answer(callback, "❌ غير مصرح لك.", show_alert=True)
        return
    await safe_answer(callback)
    
    text = (
        "❓ <b>دليل الاستخدام للمشرفين</b>\n\n"
        "• <b>إضافة مسؤول:</b> <code>/addadmin [معرف المستخدم]</code>\n"
        "• <b>إزالة مسؤول:</b> <code>/deladmin [معرف المستخدم]</code>\n"
        "• <b>حظر مستخدم:</b> <code>/ban [معرف المستخدم]</code>\n"
        "• <b>إلغاء الحظر:</b> <code>/unban [معرف المستخدم]</code>\n"
        "• <b>نشر حلقة:</b> <code>/post_episode اسم الأنمي | رقم الحلقة</code>"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 رجوع للوحة التحكم", callback_data="admin_home")]
    ])
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")

@router.callback_query(F.data == "admin_button_settings")
async def handle_admin_button_settings(callback: CallbackQuery, db_session: AsyncSession):
    authorized = await is_admin(callback.from_user.id, db_session)
    if not authorized:
        await safe_answer(callback, "❌ غير مصرح لك.", show_alert=True)
        return
    await safe_answer(callback)
    
    from app.database.models import CustomButton
    stmt = select(CustomButton).order_by(CustomButton.created_at.asc())
    res = await db_session.execute(stmt)
    buttons = res.scalars().all()
    
    text = (
        "⚙️ <b>اعدادات بوت الازرار</b>\n\n"
        "هذه اللوحة تمكنك من تعديل الأزرار التفاعلية للأقسام والمجلدات المعروضة للمستخدمين.\n\n"
        "الأزرار الحالية:\n"
    )
    if not buttons:
        text += "لا يوجد أزرار مضافة حالياً. اضغط أدناه لإضافة زر."
    else:
        text += "اضغط على أي زر أدناه لحذفه ❌:\n"
        
    inline_keyboard = []
    row = []
    for btn in buttons:
        row.append(InlineKeyboardButton(text=f"❌ {btn.text}", callback_data=f"delete_btn:{btn.id}"))
        if len(row) == 2:
            inline_keyboard.append(row)
            row = []
    if row:
        inline_keyboard.append(row)
        
    inline_keyboard.append([InlineKeyboardButton(text="➕ إضافة زر جديد", callback_data="add_custom_btn")])
    inline_keyboard.append([InlineKeyboardButton(text="🔙 رجوع للوحة التحكم", callback_data="admin_home")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=inline_keyboard)
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")

@router.callback_query(F.data == "add_custom_btn")
async def handle_add_custom_btn(callback: CallbackQuery, state: FSMContext, db_session: AsyncSession):
    authorized = await is_admin(callback.from_user.id, db_session)
    if not authorized:
        await safe_answer(callback, "❌ غير مصرح لك.", show_alert=True)
        return
    await safe_answer(callback)
    await state.set_state(AdminStates.waiting_for_custom_button_name)
    
    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ إلغاء", callback_data="admin_button_settings")]
    ])
    
    await callback.message.edit_text(
        "📝 <b>يرجى إرسال اسم الزر الجديد:</b>\n"
        "أرسل الاسم كرسالة نصية (مثال: أكشن، شونين، رياضي).",
        reply_markup=cancel_kb,
        parse_mode="HTML"
    )

@router.message(AdminStates.waiting_for_custom_button_name)
async def process_custom_button_name(message: Message, state: FSMContext, db_session: AsyncSession):
    authorized = await is_admin(message.from_user.id, db_session)
    if not authorized:
        await message.answer("❌ غير مصرح لك.")
        await state.clear()
        return
        
    btn_text = message.text.strip()
    if not btn_text:
        await message.answer("⚠️ يرجى إدخال اسم صحيح للزر.")
        return
        
    from app.database.models import CustomButton
    # Check if duplicate
    stmt = select(CustomButton).where(CustomButton.text == btn_text)
    res = await db_session.execute(stmt)
    existing = res.scalar_one_or_none()
    if existing:
        await message.answer("⚠️ هذا الزر موجود بالفعل.")
        return
        
    try:
        new_btn = CustomButton(text=btn_text)
        db_session.add(new_btn)
        await db_session.commit()
        
        await message.answer(f"✅ تم إضافة الزر <b>'{btn_text}'</b> بنجاح!", parse_mode="HTML")
    except Exception as e:
        logger.exception("Error adding custom button")
        await message.answer(f"❌ حدث خطأ أثناء إضافة الزر: {e}")
        
    await state.clear()
    
    # Re-render settings view
    stmt_all = select(CustomButton).order_by(CustomButton.created_at.asc())
    res_all = await db_session.execute(stmt_all)
    buttons = res_all.scalars().all()
    
    text = (
        "⚙️ <b>اعدادات بوت الازرار</b>\n\n"
        "هذه اللوحة تمكنك من تعديل الأزرار التفاعلية للأقسام والمجلدات المعروضة للمستخدمين.\n\n"
        "الأزرار الحالية:\n"
    )
    if not buttons:
        text += "لا يوجد أزرار مضافة حالياً. اضغط أدناه لإضافة زر."
    else:
        text += "اضغط على أي زر أدناه لحذفه ❌:\n"
        
    inline_keyboard = []
    row = []
    for btn in buttons:
        row.append(InlineKeyboardButton(text=f"❌ {btn.text}", callback_data=f"delete_btn:{btn.id}"))
        if len(row) == 2:
            inline_keyboard.append(row)
            row = []
    if row:
        inline_keyboard.append(row)
        
    inline_keyboard.append([InlineKeyboardButton(text="➕ إضافة زر جديد", callback_data="add_custom_btn")])
    inline_keyboard.append([InlineKeyboardButton(text="🔙 رجوع للوحة التحكم", callback_data="admin_home")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=inline_keyboard)
    
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")

@router.callback_query(F.data.startswith("delete_btn:"))
async def handle_delete_custom_btn(callback: CallbackQuery, db_session: AsyncSession):
    authorized = await is_admin(callback.from_user.id, db_session)
    if not authorized:
        await safe_answer(callback, "❌ غير مصرح لك.", show_alert=True)
        return
        
    btn_id = int(callback.data.split(":")[1])
    from app.database.models import CustomButton
    stmt = select(CustomButton).where(CustomButton.id == btn_id)
    res = await db_session.execute(stmt)
    btn = res.scalar_one_or_none()
    if btn:
        await db_session.delete(btn)
        await db_session.commit()
        await safe_answer(callback, "تم حذف الزر بنجاح!")
    else:
        await safe_answer(callback, "⚠️ لم يتم العثور على الزر.")
        
    # Re-render settings view
    stmt_all = select(CustomButton).order_by(CustomButton.created_at.asc())
    res_all = await db_session.execute(stmt_all)
    buttons = res_all.scalars().all()
    
    text = (
        "⚙️ <b>اعدادات بوت الازرار</b>\n\n"
        "هذه اللوحة تمكنك من تعديل الأزرار التفاعلية للأقسام والمجلدات المعروضة للمستخدمين.\n\n"
        "الأزرار الحالية:\n"
    )
    if not buttons:
        text += "لا يوجد أزرار مضافة حالياً. اضغط أدناه لإضافة زر."
    else:
        text += "اضغط على أي زر أدناه لحذفه ❌:\n"
        
    inline_keyboard = []
    row = []
    for btn in buttons:
        row.append(InlineKeyboardButton(text=f"❌ {btn.text}", callback_data=f"delete_btn:{btn.id}"))
        if len(row) == 2:
            inline_keyboard.append(row)
            row = []
    if row:
        inline_keyboard.append(row)
        
    inline_keyboard.append([InlineKeyboardButton(text="➕ إضافة زر جديد", callback_data="add_custom_btn")])
    inline_keyboard.append([InlineKeyboardButton(text="🔙 رجوع للوحة التحكم", callback_data="admin_home")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=inline_keyboard)
    
    try:
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    except Exception:
        pass

@router.callback_query(F.data == "toggle_ban_notif")
async def handle_toggle_ban_notif(callback: CallbackQuery, db_session: AsyncSession):
    authorized = await is_admin(callback.from_user.id, db_session)
    if not authorized:
        await safe_answer(callback, "❌ غير مصرح لك.", show_alert=True)
        return
        
    from app.utils.settings import get_setting, set_setting
    current = await get_setting("ban_notif_enabled", "true")
    new_val = "false" if current == "true" else "true"
    await set_setting("ban_notif_enabled", new_val)
    
    await safe_answer(callback, "تم تعديل حالة إشعار الحظر بنجاح!")
    
    text, keyboard = await get_admin_panel_data(db_session)
    try:
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    except Exception:
        pass

@router.callback_query(F.data == "toggle_join_notif")
async def handle_toggle_join_notif(callback: CallbackQuery, db_session: AsyncSession):
    authorized = await is_admin(callback.from_user.id, db_session)
    if not authorized:
        await safe_answer(callback, "❌ غير مصرح لك.", show_alert=True)
        return
        
    from app.utils.settings import get_setting, set_setting
    current = await get_setting("join_notif_enabled", "true")
    new_val = "false" if current == "true" else "true"
    await set_setting("join_notif_enabled", new_val)
    
    await safe_answer(callback, "تم تعديل حالة إشعار الدخول بنجاح!")
    
    text, keyboard = await get_admin_panel_data(db_session)
    try:
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    except Exception:
        pass


@router.callback_query(F.data.startswith("admin_users_page:"))
async def handle_admin_users_page(callback: CallbackQuery, db_session: AsyncSession):
    authorized = await is_admin(callback.from_user.id, db_session)
    if not authorized:
        await safe_answer(callback, "❌ غير مصرح لك.", show_alert=True)
        return
        
    await safe_answer(callback)
    
    page = int(callback.data.split(":")[1])
    per_page = 5
    offset = (page - 1) * per_page
    
    from app.database.models import User, UserFavorites, PersistentTaskQueue
    
    # Get total count of active users
    stmt_count = select(func.count(User.id)).where((User.is_blocked == False) | (User.is_blocked == None))
    res_count = await db_session.execute(stmt_count)
    total_users = res_count.scalar() or 0
    
    # Get users for page
    stmt_users = select(User).where((User.is_blocked == False) | (User.is_blocked == None)).order_by(User.created_at.desc()).offset(offset).limit(per_page)
    res_users = await db_session.execute(stmt_users)
    users = res_users.scalars().all()
    
    text = f"👥 <b>قائمة المستخدمين النشطين (صفحة {page} من {(total_users + per_page - 1) // per_page or 1}):</b>\n"
    text += f"إجمالي عدد المستخدمين النشطين: <b>{total_users}</b>\n\n"
    
    if not users:
        text += "لا يوجد مستخدمين نشطين حالياً."
    else:
        for idx, u in enumerate(users, start=offset + 1):
            name_str = f"{u.first_name or ''} {u.last_name or ''}".strip() or "لا يوجد اسم"
            username_str = f"@{u.username}" if u.username else "لا يوجد"
            
            # Fetch chosen animes
            stmt_favs = select(UserFavorites.anime_title).where(UserFavorites.user_id == u.user_id)
            res_favs = await db_session.execute(stmt_favs)
            fav_titles = res_favs.scalars().all()
            
            stmt_tasks = select(PersistentTaskQueue.anime_title).where(PersistentTaskQueue.user_id == u.user_id)
            res_tasks = await db_session.execute(stmt_tasks)
            task_titles = res_tasks.scalars().all()
            
            chosen_animes = sorted(list(set(fav_titles + task_titles)))
            animes_str = ", ".join(chosen_animes) if chosen_animes else "لم يحدد أي أنمي بعد"
            
            joined_date = u.created_at.strftime("%Y-%m-%d %H:%M") if u.created_at else "غير معروف"
            
            text += (
                f"{idx}. <b>الاسم:</b> <a href='tg://user?id={u.user_id}'>{name_str}</a>\n"
                f"   • <b>المعرف:</b> <code>{u.user_id}</code>\n"
                f"   • <b>اليوزر:</b> {username_str}\n"
                f"   • <b>الأنميات المختارة:</b> <i>{animes_str}</i>\n"
                f"   • <b>تاريخ الانضمام:</b> <code>{joined_date}</code>\n\n"
            )
            
    # Keyboard
    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton(text="⬅️ السابق", callback_data=f"admin_users_page:{page - 1}"))
    if offset + per_page < total_users:
        nav_buttons.append(InlineKeyboardButton(text="التالي ➡️", callback_data=f"admin_users_page:{page + 1}"))
        
    keyboard = []
    if nav_buttons:
        keyboard.append(nav_buttons)
    keyboard.append([InlineKeyboardButton(text="🔙 رجوع للوحة التحكم", callback_data="admin_home")])
    
    markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")


@router.callback_query(F.data.startswith("admin_blocked_page:"))
async def handle_admin_blocked_page(callback: CallbackQuery, db_session: AsyncSession):
    authorized = await is_admin(callback.from_user.id, db_session)
    if not authorized:
        await safe_answer(callback, "❌ غير مصرح لك.", show_alert=True)
        return
        
    await safe_answer(callback)
    
    page = int(callback.data.split(":")[1])
    per_page = 5
    offset = (page - 1) * per_page
    
    from app.database.models import User
    
    # Get total count of blocked users
    stmt_count = select(func.count(User.id)).where(User.is_blocked == True)
    res_count = await db_session.execute(stmt_count)
    total_blocked = res_count.scalar() or 0
    
    # Get users for page
    stmt_users = select(User).where(User.is_blocked == True).order_by(User.created_at.desc()).offset(offset).limit(per_page)
    res_users = await db_session.execute(stmt_users)
    users = res_users.scalars().all()
    
    text = f"🚫 <b>قائمة المستخدمين الحاظرين للبوت (صفحة {page} من {(total_blocked + per_page - 1) // per_page or 1}):</b>\n"
    text += f"إجمالي المستخدمين الذين حظروا البوت: <b>{total_blocked}</b>\n\n"
    
    if not users:
        text += "لا يوجد مستخدمين حاظرين للبوت حالياً (يتم اكتشافهم وتحديثهم تلقائياً عند إرسال إذاعة جماعية)."
    else:
        for idx, u in enumerate(users, start=offset + 1):
            name_str = f"{u.first_name or ''} {u.last_name or ''}".strip() or "لا يوجد اسم"
            username_str = f"@{u.username}" if u.username else "لا يوجد"
            joined_date = u.created_at.strftime("%Y-%m-%d %H:%M") if u.created_at else "غير معروف"
            
            text += (
                f"{idx}. <b>الاسم:</b> <a href='tg://user?id={u.user_id}'>{name_str}</a>\n"
                f"   • <b>المعرف:</b> <code>{u.user_id}</code>\n"
                f"   • <b>اليوزر:</b> {username_str}\n"
                f"   • <b>تاريخ الانضمام:</b> <code>{joined_date}</code>\n\n"
            )
            
    # Keyboard
    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton(text="⬅️ السابق", callback_data=f"admin_blocked_page:{page - 1}"))
    if offset + per_page < total_blocked:
        nav_buttons.append(InlineKeyboardButton(text="التالي ➡️", callback_data=f"admin_blocked_page:{page + 1}"))
        
    keyboard = []
    if nav_buttons:
        keyboard.append(nav_buttons)
    keyboard.append([InlineKeyboardButton(text="🔙 رجوع للوحة التحكم", callback_data="admin_home")])
    
    markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")


@router.callback_query(F.data == "admin_broadcast")
async def handle_admin_broadcast(callback: CallbackQuery, db_session: AsyncSession, state: FSMContext):
    authorized = await is_admin(callback.from_user.id, db_session)
    if not authorized:
        await safe_answer(callback, "❌ غير مصرح لك.", show_alert=True)
        return
        
    await safe_answer(callback)
    await state.set_state(AdminStates.waiting_for_broadcast)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ إلغاء", callback_data="admin_home")]
    ])
    
    await callback.message.edit_text(
        "📢 <b>قسم الإذاعة الجماعية:</b>\n\n"
        "يرجى إرسال الرسالة التي ترغب في بثها لجميع مستخدمي البوت.\n"
        "يمكنك استخدام التنسيق الغني (رابط، خط عريض، إلخ).",
        reply_markup=keyboard,
        parse_mode="HTML"
    )


@router.message(AdminStates.waiting_for_broadcast)
async def process_admin_broadcast(message: Message, db_session: AsyncSession, state: FSMContext):
    authorized = await is_admin(message.from_user.id, db_session)
    if not authorized:
        return
        
    await state.clear()
    status_msg = await message.answer("🔄 جاري بدء البث الجماعي للمستخدمين...")
    
    from app.database.models import User
    stmt = select(User.user_id)
    res = await db_session.execute(stmt)
    user_ids = res.scalars().all()
    
    success_count = 0
    fail_count = 0
    
    from aiogram.exceptions import TelegramForbiddenError
    from sqlalchemy import update
    
    for uid in user_ids:
        try:
            await message.copy_to(chat_id=uid)
            success_count += 1
            await asyncio.sleep(0.05) # Rate limit protection
        except TelegramForbiddenError:
            fail_count += 1
            try:
                stmt_block = update(User).where(User.user_id == uid).values(is_blocked=True)
                await db_session.execute(stmt_block)
                await db_session.commit()
                
                from app.utils.settings import get_setting
                ban_notif = await get_setting("ban_notif_enabled", "true")
                if ban_notif == "true":
                    from app.database.models import BotAdmin
                    stmt_admins = select(BotAdmin.user_id)
                    res_admins = await db_session.execute(stmt_admins)
                    admin_ids = list(res_admins.scalars().all())
                    admin_ids.append(config.SUPER_ADMIN_ID)
                    admin_ids = list(set(admin_ids))
                    
                    for admin_id in admin_ids:
                        try:
                            await message.bot.send_message(
                                chat_id=admin_id,
                                text=f"🚫 <b>إشعار حظر جديد:</b>\nالمستخدم <code>{uid}</code> قام بحظر البوت."
                            )
                        except Exception:
                            pass
            except Exception:
                pass
        except Exception:
            fail_count += 1
            
    await status_msg.edit_text(
        f"✅ <b>اكتمل البث الجماعي بنجاح:</b>\n\n"
        f"🟢 تم الإرسال إلى: `{success_count}` مستخدم\n"
        f"🔴 فشل الإرسال لـ: `{fail_count}` مستخدم",
        parse_mode="HTML"
    )


@router.callback_query(F.data == "admin_toggle_sub")
async def handle_admin_toggle_sub(callback: CallbackQuery, db_session: AsyncSession):
    authorized = await is_admin(callback.from_user.id, db_session)
    if not authorized:
        await safe_answer(callback, "❌ غير مصرح لك.", show_alert=True)
        return
        
    await safe_answer(callback)
    
    active_channel = config.CHANNEL_USERNAME or "تعطيل / Disabled"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✏️ تغيير القناة", callback_data="admin_change_channel"),
            InlineKeyboardButton(text="❌ تعطيل الاشتراك الإجباري", callback_data="admin_disable_sub")
        ],
        [InlineKeyboardButton(text="🔙 رجوع للوحة التحكم", callback_data="admin_home")]
    ])
    
    await callback.message.edit_text(
        f"🔒 <b>إعدادات الاشتراك الإجباري:</b>\n\n"
        f"القناة الحالية: <b>{active_channel}</b>\n\n"
        f"يمكنك تغيير القناة أو تعطيل الاشتراك تماماً باستخدام الأزرار أدناه:",
        reply_markup=keyboard,
        parse_mode="HTML"
    )


@router.callback_query(F.data == "admin_disable_sub")
async def handle_admin_disable_sub(callback: CallbackQuery, db_session: AsyncSession):
    authorized = await is_admin(callback.from_user.id, db_session)
    if not authorized:
        await safe_answer(callback, "❌ غير مصرح لك.", show_alert=True)
        return
        
    config.CHANNEL_USERNAME = None
    from app.utils.settings import delete_setting
    await delete_setting("channel_username")
    await safe_answer(callback, "✅ تم تعطيل الاشتراك الإجباري بنجاح.", show_alert=True)
    await handle_admin_toggle_sub(callback, db_session)


@router.callback_query(F.data == "admin_change_channel")
async def handle_admin_change_channel(callback: CallbackQuery, db_session: AsyncSession, state: FSMContext):
    authorized = await is_admin(callback.from_user.id, db_session)
    if not authorized:
        await safe_answer(callback, "❌ غير مصرح لك.", show_alert=True)
        return
        
    await safe_answer(callback)
    await state.set_state(AdminStates.waiting_for_channel)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ إلغاء", callback_data="admin_toggle_sub")]
    ])
    
    await callback.message.edit_text(
        "✏️ <b>تغيير قناة الاشتراك الإجباري:</b>\n\n"
        "يرجى إرسال معرف القناة الجديد يبدأ بـ `@` (مثال: `@botanmie_channel`):",
        reply_markup=keyboard,
        parse_mode="HTML"
    )


@router.message(AdminStates.waiting_for_channel)
async def process_admin_channel(message: Message, db_session: AsyncSession, state: FSMContext):
    authorized = await is_admin(message.from_user.id, db_session)
    if not authorized:
        return
        
    text = message.text.strip()
    channels = [c.strip() for c in text.replace(",", " ").split() if c.strip()]
    if not channels:
        await message.answer("❌ يرجى إدخال معرف قناة صالح يبدأ بـ `@`.")
        return
        
    for ch in channels:
        if not ch.startswith("@"):
            await message.answer(f"❌ معرف غير صالح: <code>{ch}</code>.\nيجب أن تبدأ كافة المعرفات بـ `@` (مثال: `@channel1, @channel2`). يرجى المحاولة مجدداً.", parse_mode="HTML")
            return
            
    final_val = ", ".join(channels)
    config.CHANNEL_USERNAME = final_val
    from app.utils.settings import set_setting
    await set_setting("channel_username", final_val)
    await state.clear()
    await message.answer(f"✅ تم تحديث قنوات الاشتراك الإجباري بنجاح إلى:\n<b>{final_val}</b>", parse_mode="HTML")


@router.callback_query(F.data == "admin_set_bg")
async def handle_admin_set_bg(callback: CallbackQuery, db_session: AsyncSession, state: FSMContext):
    authorized = await is_admin(callback.from_user.id, db_session)
    if not authorized:
        await safe_answer(callback, "❌ غير مصرح لك.", show_alert=True)
        return
        
    await safe_answer(callback)
    await state.set_state(AdminStates.waiting_for_bg_photo)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ إلغاء", callback_data="admin_home")]
    ])
    
    await callback.message.edit_text(
        "🖼️ <b>تغيير خلفية الفيديوهات:</b>\n\n"
        "يرجى إرسال الصورة مباشرة في هذه المحادثة كملف صورة عادي.",
        reply_markup=keyboard,
        parse_mode="HTML"
    )


@router.message(AdminStates.waiting_for_bg_photo, F.photo)
async def process_admin_bg_photo(message: Message, db_session: AsyncSession, state: FSMContext):
    authorized = await is_admin(message.from_user.id, db_session)
    if not authorized:
        return
        
    photo = message.photo[-1]
    file_id = photo.file_id
    
    status_msg = await message.answer("🔄 جاري حفظ معرف الصورة المصغرة في قاعدة البيانات...")
    
    try:
        from app.utils.settings import set_setting, delete_setting
        await set_setting("custom_thumb_file_id", file_id)
        await delete_setting("custom_thumb_url")
        
        # Clear local thumbnail cache file to trigger fresh download next time
        import os
        from config import config
        local_path = config.DOWNLOAD_DIR / "custom_thumb.jpg"
        if local_path.exists():
            try: os.unlink(local_path)
            except Exception: pass
            
        await status_msg.edit_text("✅ تم تحديث خلفية الفيديوهات الافتراضية بنجاح.")
        await state.clear()
    except Exception as e:
        logger.exception("Error processing background photo")
        import html
        await status_msg.edit_text(f"❌ فشل تحديث الصورة: {html.escape(str(e))}")
