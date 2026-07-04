from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pathlib import Path

from config import config
from app.database.models import BotAdmin
from app.utils.auth import is_admin
from app.utils.logging_config import logger

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

@router.message(F.photo)
async def handle_custom_thumbnail(message: Message, db_session: AsyncSession):
    authorized = await is_admin(message.from_user.id, db_session)
    if not authorized:
        await message.answer("❌ عذراً، لا تملك الصلاحية لتغيير الصورة المصغرة للفيديو.")
        return
        
    status_msg = await message.answer("🔄 جاري تنزيل الصورة من خادم تلغرام السحابي وتحديث الخلفية...")
    
    # Ensure app/data directory exists
    data_dir = Path(__file__).parent.parent / "data"
    data_dir.mkdir(exist_ok=True)
    thumb_path = data_dir / "custom_thumb.jpg"
    thumb_id_path = data_dir / "custom_thumb_id.txt"
    
    try:
        photo = message.photo[-1]
        file_id = photo.file_id
        bot_token = message.bot.token
        
        import aiohttp
        # 1. Fetch file info from official cloud Telegram API
        get_file_url = f"https://api.telegram.org/bot{bot_token}/getFile?file_id={file_id}"
        async with aiohttp.ClientSession() as session:
            async with session.get(get_file_url, ssl=False, timeout=15) as resp:
                if resp.status != 200:
                    await status_msg.edit_text(f"❌ فشل جلب معلومات الملف من تلغرام السحابي. كود الحالة: {resp.status}")
                    return
                file_info = await resp.json()
                
        if not file_info.get("ok"):
            await status_msg.edit_text("❌ رد غير صالح من خادم تلغرام السحابي.")
            return
            
        file_path = file_info["result"]["file_path"]
        
        # 2. Download the image bytes from official cloud file server
        download_url = f"https://api.telegram.org/file/bot{bot_token}/{file_path}"
        async with aiohttp.ClientSession() as session:
            async with session.get(download_url, ssl=False, timeout=30) as resp:
                if resp.status == 200:
                    image_bytes = await resp.read()
                    with open(thumb_path, "wb") as f:
                        f.write(image_bytes)
                        
                    # Clean up custom_thumb_id.txt if it exists to avoid conflicts
                    if thumb_id_path.exists():
                        thumb_id_path.unlink()
                        
                    logger.info(f"Custom video thumbnail updated by Admin (User ID: {message.from_user.id}) via sent Photo message.")
                    await status_msg.edit_text("✅ تم تحديث الخلفية الافتراضية للفيديوهات بنجاح من الصورة المرسلة!")
                else:
                    await status_msg.edit_text(f"❌ فشل تنزيل ملف الصورة من خادم تلغرام. كود الحالة: {resp.status}")
    except Exception as e:
        logger.exception("Error downloading custom thumbnail from Telegram cloud API")
        import html
        await status_msg.edit_text(f"❌ فشل تحديث الصورة المصغرة: {html.escape(str(e))}")

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
        
    status_msg = await message.answer("🔄 جاري تحميل وحفظ الصورة المصغرة من الرابط...")
    
    # Ensure app/data directory exists
    data_dir = Path(__file__).parent.parent / "data"
    data_dir.mkdir(exist_ok=True)
    thumb_path = data_dir / "custom_thumb.jpg"
    thumb_id_path = data_dir / "custom_thumb_id.txt"
    
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
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(target_url, ssl=False, timeout=30) as resp:
                if resp.status == 200:
                    image_bytes = await resp.read()
                    with open(thumb_path, "wb") as f:
                        f.write(image_bytes)
                    
                    # Clean up custom_thumb_id.txt if it exists to avoid conflicts
                    if thumb_id_path.exists():
                        thumb_id_path.unlink()
                        
                    logger.info(f"Custom video thumbnail updated by Admin (User ID: {message.from_user.id}) via URL: {target_url}")
                    await status_msg.edit_text("✅ تم تحميل وتحديث الصورة المصغرة الافتراضية للفيديوهات بنجاح.")
                else:
                    await status_msg.edit_text(f"❌ فشل تحميل الصورة، رمز استجابة السيرفر: {resp.status}")
    except Exception as e:
        logger.exception("Error downloading custom thumbnail from URL")
        import html
        await status_msg.edit_text(f"❌ فشل تحميل الصورة: {html.escape(str(e))}")

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
            scraper_results = await search_anime_scraper(anime["title_romaji"])
            if not scraper_results and anime["title_english"]:
                scraper_results = await search_anime_scraper(anime["title_english"])
            if scraper_results:
                anime_slug = get_best_slug_match(scraper_results, anime["title_romaji"] or anime["title_english"])
        else:
            # Fallback direct search on scraper
            scraper_results = await search_anime_scraper(anime_query)
            if scraper_results:
                anime_slug = get_best_slug_match(scraper_results, anime_query)
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
        
        if image_url:
            await message.bot.send_photo(
                chat_id=config.CHANNEL_USERNAME,
                photo=image_url,
                caption=caption,
                reply_markup=markup,
                parse_mode="HTML"
            )
        else:
            await message.bot.send_message(
                chat_id=config.CHANNEL_USERNAME,
                text=caption,
                reply_markup=markup,
                parse_mode="HTML"
            )
            
        await status_msg.edit_text(f"✅ تم نشر الحلقة بنجاح في القناة: {config.CHANNEL_USERNAME}")
        
    except Exception as e:
        logger.exception("Error broadcasting episode to channel")
        import html
        await status_msg.edit_text(f"❌ حدث خطأ أثناء البث: {html.escape(str(e))}")
