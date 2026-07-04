import random
from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from config import config
from aiogram.exceptions import TelegramBadRequest

router = Router(name="start")

SUGGESTIONS = [
    "One Piece", "Naruto Shippuden", "Attack on Titan", "Hunter x Hunter", 
    "Jujutsu Kaisen", "Demon Slayer", "Death Note", "My Hero Academia",
    "Bleach", "Fullmetal Alchemist: Brotherhood", "Tokyo Ghoul", "Dragon Ball Super",
    "Vinland Saga", "Chainsaw Man", "Solo Leveling", "Frieren: Beyond Journey's End",
    "Steins;Gate", "Monster", "Code Geass", "Haikyuu!!", "One Punch Man"
]

async def send_welcome_panel(message: Message, db_session: AsyncSession):
    from app.utils.auth import is_admin
    user_id = message.from_user.id
    is_user_admin = await is_admin(user_id, db_session)
    
    keyboard = [
        [
            InlineKeyboardButton(text="🔍 بحث", callback_data="menu_search"),
            InlineKeyboardButton(text="🎲 إقترح لي", callback_data="menu_suggest")
        ],
        [
            InlineKeyboardButton(text="⭐ قائمة المفضلة", callback_data="menu_favorites")
        ],
        [
            InlineKeyboardButton(text="🛠️ الدعم الفني", callback_data="menu_support"),
            InlineKeyboardButton(text="❓ مساعدة", callback_data="menu_help")
        ],
        [
            InlineKeyboardButton(text="📢 للإعلانات والتمويل", callback_data="menu_ads")
        ]
    ]
    
    welcome_text = (
        "✨ <b>أهلاً بك في بوت أنمي وانمي | Anime & Anmie</b> 🎬\n\n"
        "مرحباً بك في وجهتك الأولى لمشاهدة وتحميل الأنمي بجودة عالية وسرعة فائقة! 🚀\n"
        "البوت يدعم البحث الذكي (بالعربية والإنجليزية وأسماء الشخصيات) وتنزيل الحلقات مباشرة داخل تلغرام بأحجام تصل إلى 2 جيجابايت.\n\n"
    )
    
    if is_user_admin:
        keyboard.append([InlineKeyboardButton(text="🛠️ لوحة تحكم الإدارة (Admin)", callback_data="admin_home")])
        welcome_text += (
            "🛠️ <b>قسم الإدارة والمسؤولين:</b>\n"
            "مرحباً بك كمسؤول في البوت. إليك الأوامر المتاحة لك:\n"
            "• <code>/admin</code> - فتح لوحة التحكم الشاملة.\n"
            "• <code>/addadmin &lt;ID&gt;</code> - إضافة مسؤول جديد.\n"
            "• <code>/deladmin &lt;ID&gt;</code> - إزالة مسؤول.\n"
            "• <code>/post_episode &lt;anime&gt; | &lt;episode&gt;</code> - بث ونشر حلقة جديدة في القناة.\n"
            "• <code>/setthumb &lt;URL&gt;</code> - تعيين خلفية فيديو افتراضية من رابط.\n\n"
        )
        
    welcome_text += "👇 <b>اختر من القائمة أدناه لبدء المغامرة:</b>"
    
    markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    await message.answer(welcome_text, reply_markup=markup, parse_mode="HTML")

@router.message(CommandStart())
async def cmd_start(message: Message, db_session: AsyncSession, state: FSMContext):
    """Handles the /start command, supporting deep linking."""
    from app.database.models import User
    from sqlalchemy import select
    from app.utils.logging_config import logger
    try:
        user_id = message.from_user.id
        username = message.from_user.username
        stmt_user = select(User).where(User.user_id == user_id)
        res_user = await db_session.execute(stmt_user)
        existing_user = res_user.scalar_one_or_none()
        if not existing_user:
            new_user = User(user_id=user_id, username=username)
            db_session.add(new_user)
            await db_session.commit()
            logger.info(f"Registered new user in database: {user_id}")
    except Exception:
        logger.exception("Error saving user to database on /start")

    args = message.text.split()
    if len(args) > 1:
        deep_link = args[1]
        if deep_link.startswith("dl_"):
            try:
                cache_id = int(deep_link.split("_")[1])
                from sqlalchemy import select
                from app.database.models import DownloadCache, EpisodeCache
                
                stmt = select(DownloadCache).where(DownloadCache.id == cache_id)
                res = await db_session.execute(stmt)
                dl_cache = res.scalar_one_or_none()
                
                if dl_cache:
                    await state.clear()
                    
                    stmt_ep = select(EpisodeCache).where(EpisodeCache.play_url == dl_cache.play_url)
                    res_ep = await db_session.execute(stmt_ep)
                    ep_entry = res_ep.scalar_one_or_none()
                    anilist_id = ep_entry.anilist_id if ep_entry else 0
                    ep_number = ep_entry.ep_number if ep_entry else "1"
                    
                    from config import config
                    from aiogram.types import WebAppInfo
                    webapp_url = f"{config.WEBAPP_BASE_URL}/webapp/qualities?db_cache_id={dl_cache.id}&anilist_id={anilist_id}&ep_number={ep_number}"
                    
                    keyboard_buttons = [
                        [InlineKeyboardButton(text="⚙️ اختر الجودة", web_app=WebAppInfo(url=webapp_url))]
                    ]
                    markup = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
                    
                    anime_title = "أنمي"
                    try:
                        from urllib.parse import unquote
                        decoded = unquote(dl_cache.play_url)
                        parts = [p for p in decoded.strip("/").split("/") if p]
                        if parts:
                            slug_part = parts[-1]
                            if "الحلقة" in slug_part:
                                ep_parts = slug_part.split("الحلقة")
                                ep_num = ep_parts[-1].strip("-").strip()
                                anime_slug = ep_parts[0].strip("-").strip()
                                anime_title = f"{anime_slug.replace('-', ' ').title()} - الحلقة {ep_num}"
                            else:
                                anime_title = slug_part.replace("-", " ").title()
                    except Exception:
                        pass
                        
                    await message.answer(
                        f"🎬 **الأنمي**: {anime_title}\n\n"
                        f"اختر جودة التحميل المفضلة أدناه:",
                        reply_markup=markup,
                        parse_mode="Markdown"
                    )
                    return
                else:
                    await message.answer("❌ عذراً، انتهت صلاحية هذا الرابط أو لم يعد متوفراً.")
            except Exception:
                from app.utils.logging_config import logger
                logger.exception("Error handling deep link")
                await message.answer("❌ حدث خطأ أثناء معالجة رابط التحميل المباشر.")
                return

    await send_welcome_panel(message, db_session)

@router.message(Command("help"))
async def cmd_help(message: Message):
    """Handles the /help command."""
    help_text = (
        "ℹ️ <b>دليل وتعليمات استخدام البوت كعضو:</b>\n\n"
        "🤖 <b>الأوامر المتاحة لك:</b>\n"
        "• <code>/start</code> - لتشغيل البوت وفتح لوحة التحكم الترحيبية.\n"
        "• <code>/help</code> - لعرض دليل الاستخدام والتعليمات المفصلة.\n\n"
        "📖 <b>خطوات استخدام البوت والتحميل:</b>\n"
        "1️⃣ <b>البحث</b>: أرسل اسم الأنمي مباشرة في الدردشة (باللغة العربية أو الإنجليزية أو اسم الشخصية). مثال: <code>Demon Slayer</code>.\n"
        "2️⃣ <b>اختيار الأنمي</b>: ستظهر لك قائمة بالأنميات المتطابقة، اضغط على زر الأنمي المطلوب.\n"
        "3️⃣ <b>اختيار الحلقة</b>: سيقوم البوت بتقسيم الحلقات تلقائياً لمجموعات، اضغط على المجموعة ثم اختر رقم الحلقة المطلوب فوراً من لوحة الأزرار.\n"
        "4️⃣ <b>اختيار جودة التحميل</b>: اختر الجودة المناسبة لك (1080p، 720p، 480p, 360p) أو اختر <b>'تلقائي'</b> ليقوم البوت بضغط وتحديد جودة الفيديو تلقائياً لتناسب السيرفر.\n\n"
        "💡 <b>ميزات ذكية إضافية:</b>\n"
        "• <b>قائمة المفضلة</b>: يمكنك حفظ الأنميات التي تتابعها بالضغط على '⭐ إضافة إلى المفضلة' للوصول إليها لاحقاً بضغطة زر.\n"
        "• <b>أزرار التنقل السريعة</b>: عند استلام الفيديو، ستجد أزرار تنقل تحت الفيديو مباشرة (`◀️ الحلقة السابقة` | `🔢 حلقة أخرى` | `▶️ الحلقة التالية`) لتشغيل الحلقة التالية بلمسة واحدة دون البحث مجدداً.\n"
        "• <b>سرعة ودعم فائق</b>: يدعم البوت تنزيل الحلقات والأفلام ذات الأحجام الضخمة حتى 2 جيجابايت لتلبي كافة الاحتياجات."
    )
    await message.answer(help_text, parse_mode="HTML")

@router.callback_query(F.data == "check_sub")
async def handle_check_subscription(callback: CallbackQuery, db_session: AsyncSession):
    bot = callback.bot
    user_id = callback.from_user.id
    
    if not config.CHANNEL_USERNAME:
        await callback.answer("تم التحقق بنجاح! البوت مفعل للجميع.")
        try:
            await callback.bot.delete_message(chat_id=callback.message.chat.id, message_id=callback.message.message_id)
        except Exception:
            pass
        await send_welcome_panel(callback.message, db_session)
        return
        
    try:
        member = await bot.get_chat_member(chat_id=config.CHANNEL_USERNAME, user_id=user_id)
        if member.status in ("member", "administrator", "creator"):
            await callback.answer("✅ تم التحقق بنجاح! شكراً لاشتراكك.", show_alert=True)
            try:
                await callback.bot.delete_message(chat_id=callback.message.chat.id, message_id=callback.message.message_id)
            except Exception:
                pass
            await send_welcome_panel(callback.message, db_session)
        else:
            await callback.answer("❌ لم تشترك في القناة بعد! يرجى الاشتراك أولاً.", show_alert=True)
    except Exception:
        from app.utils.logging_config import logger
        logger.warning(f"Error checking sub in callback for user {user_id}")
        await callback.answer("✅ تم التفعيل بنجاح!")
        try:
            await callback.bot.delete_message(chat_id=callback.message.chat.id, message_id=callback.message.message_id)
        except Exception:
            pass
        await send_welcome_panel(callback.message, db_session)

@router.callback_query(F.data == "menu_search")
async def handle_menu_search(callback: CallbackQuery):
    await callback.answer()
    try:
        await callback.message.edit_text("🔍 **أرسل اسم الأنمي الذي تريد البحث عنه الآن (بالعربية أو الإنجليزية):**", parse_mode="Markdown")
    except TelegramBadRequest:
        await callback.message.answer("🔍 **أرسل اسم الأنمي الذي تريد البحث عنه الآن (بالعربية أو الإنجليزية):**", parse_mode="Markdown")

@router.callback_query(F.data == "menu_suggest")
async def handle_menu_suggest(callback: CallbackQuery):
    await callback.answer()
    suggested = random.choice(SUGGESTIONS)
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🔍 ابحث عن {suggested}", callback_data=f"suggest_search:{suggested}")],
        [InlineKeyboardButton(text="🏠 العودة للرئيسية", callback_data="check_sub")]
    ])
    try:
        await callback.message.edit_text(
            f"🎲 <b>اقتراح اليوم لك:</b>\n\n"
            f"📺 أنمي: <b>{suggested}</b>\n\n"
            f"اضغط على الزر بالأسفل للبحث عنه تلقائياً 👇",
            reply_markup=markup,
            parse_mode="HTML"
        )
    except TelegramBadRequest:
        await callback.message.answer(
            f"🎲 <b>اقتراح اليوم لك:</b>\n\n"
            f"📺 أنمي: <b>{suggested}</b>\n\n"
            f"اضغط على الزر بالأسفل للبحث عنه تلقائياً 👇",
            reply_markup=markup,
            parse_mode="HTML"
        )

@router.callback_query(F.data.startswith("suggest_search:"))
async def handle_suggest_search(callback: CallbackQuery, db_session: AsyncSession, state: FSMContext):
    await callback.answer()
    query = callback.data.split(":", 1)[1]
    from app.handlers.search import handle_anime_search
    fake_msg = Message(
        message_id=callback.message.message_id,
        date=callback.message.date,
        chat=callback.message.chat,
        from_user=callback.from_user,
        text=query
    ).as_(callback.bot)
    await handle_anime_search(fake_msg, db_session, state)

@router.callback_query(F.data == "menu_favorites")
async def handle_menu_favorites(callback: CallbackQuery, db_session: AsyncSession):
    await callback.answer()
    user_id = callback.from_user.id
    from sqlalchemy import select
    from app.database.models import UserFavorites
    
    stmt = select(UserFavorites).where(UserFavorites.user_id == user_id)
    res = await db_session.execute(stmt)
    favs = res.scalars().all()
    
    keyboard = []
    if not favs:
        text = "⭐ <b>قائمة المفضلة فارغة حالياً.</b>\nيمكنك إضافة أي أنمي للمفضلة عند البحث عنه وعرض تفاصيله!"
    else:
        text = "⭐ <b>قائمة الأنميات المفضلة لديك:</b>\n\n"
        for f in favs:
            keyboard.append([InlineKeyboardButton(text=f.anime_title, callback_data=f"suggest_search:{f.anime_title}")])
            
    keyboard.append([InlineKeyboardButton(text="🏠 العودة للرئيسية", callback_data="check_sub")])
    markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    try:
        await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=markup, parse_mode="HTML")

@router.callback_query(F.data == "menu_support")
async def handle_menu_support(callback: CallbackQuery):
    await callback.answer()
    support_text = (
        "🛠️ <b>الدعم الفني والتواصل:</b>\n\n"
        "إذا واجهتك أي مشكلة في استخدام البوت أو استخراج الروابط، يرجى التواصل معنا عبر المعرف التالي:\n"
        "👉 @botanmie_support\n\n"
        "نشكرك على استخدام خدماتنا! ❤️"
    )
    keyboard = [[InlineKeyboardButton(text="🏠 العودة للرئيسية", callback_data="check_sub")]]
    markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    try:
        await callback.message.edit_text(support_text, reply_markup=markup, parse_mode="HTML")
    except Exception:
        await callback.message.answer(support_text, reply_markup=markup, parse_mode="HTML")

@router.callback_query(F.data == "menu_help")
async def handle_menu_help(callback: CallbackQuery):
    await callback.answer()
    help_text = (
        "ℹ️ <b>دليل وتعليمات استخدام البوت كعضو:</b>\n\n"
        "🤖 <b>الأوامر المتاحة لك:</b>\n"
        "• <code>/start</code> - لتشغيل البوت وفتح لوحة التحكم الترحيبية.\n"
        "• <code>/help</code> - لعرض دليل الاستخدام والتعليمات المفصلة.\n\n"
        "📖 <b>خطوات استخدام البوت والتحميل:</b>\n"
        "1️⃣ <b>البحث</b>: أرسل اسم الأنمي مباشرة في الدردشة (باللغة العربية أو الإنجليزية أو اسم الشخصية). مثال: <code>Demon Slayer</code>.\n"
        "2️⃣ <b>اختيار الأنمي</b>: ستظهر لك قائمة بالأنميات المتطابقة، اضغط على زر الأنمي المطلوب.\n"
        "3️⃣ <b>اختيار الحلقة</b>: سيقوم البوت بتقسيم الحلقات تلقائياً لمجموعات، اضغط على المجموعة ثم اختر رقم الحلقة المطلوب فوراً من لوحة الأزرار.\n"
        "4️⃣ <b>اختيار جودة التحميل</b>: اختر الجودة المناسبة لك (1080p، 720p، 480p, 360p) أو اختر <b>'تلقائي'</b> ليقوم البوت بضغط وتحديد جودة الفيديو تلقائياً لتناسب السيرفر.\n\n"
        "💡 <b>ميزات ذكية إضافية:</b>\n"
        "• <b>قائمة المفضلة</b>: يمكنك حفظ الأنميات التي تتابعها بالضغط على '⭐ إضافة إلى المفضلة' للوصول إليها لاحقاً بضغطة زر.\n"
        "• <b>أزرار التنقل السريعة</b>: عند استلام الفيديو، ستجد أزرار تنقل تحت الفيديو مباشرة (`◀️ الحلقة السابقة` | `🔢 حلقة أخرى` | `▶️ الحلقة التالية`) لتشغيل الحلقة التالية بلمسة واحدة دون البحث مجدداً.\n"
        "• <b>سرعة ودعم فائق</b>: يدعم البوت تنزيل الحلقات والأفلام ذات الأحجام الضخمة حتى 2 جيجابايت لتلبي كافة الاحتياجات."
    )
    keyboard = [[InlineKeyboardButton(text="🏠 العودة للرئيسية", callback_data="check_sub")]]
    markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    try:
        await callback.message.edit_text(help_text, reply_markup=markup, parse_mode="HTML")
    except Exception:
        await callback.message.answer(help_text, reply_markup=markup, parse_mode="HTML")

@router.callback_query(F.data == "menu_ads")
async def handle_menu_ads(callback: CallbackQuery):
    await callback.answer()
    ads_text = (
        "📢 <b>للإعلانات والتمويل والتبرع:</b>\n\n"
        "لدعم استمرار خوادم البوت وتطويره، أو لطلب مساحات إعلانية داخل البوت والقناة، يرجى التواصل مع الإدارة:\n"
        "👉 @botanmie_admin\n\n"
        "رأيكم ودعمكم يهمنا! 🌟"
    )
    keyboard = [[InlineKeyboardButton(text="🏠 العودة للرئيسية", callback_data="check_sub")]]
    markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    try:
        await callback.message.edit_text(ads_text, reply_markup=markup, parse_mode="HTML")
    except Exception:
        await callback.message.answer(ads_text, reply_markup=markup, parse_mode="HTML")
