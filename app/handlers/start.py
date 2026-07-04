import random
from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from config import config

router = Router(name="start")

SUGGESTIONS = [
    "One Piece", "Naruto Shippuden", "Attack on Titan", "Hunter x Hunter", 
    "Jujutsu Kaisen", "Demon Slayer", "Death Note", "My Hero Academia",
    "Bleach", "Fullmetal Alchemist: Brotherhood", "Tokyo Ghoul", "Dragon Ball Super",
    "Vinland Saga", "Chainsaw Man", "Solo Leveling", "Frieren: Beyond Journey's End",
    "Steins;Gate", "Monster", "Code Geass", "Haikyuu!!", "One Punch Man"
]

def get_welcome_markup() -> InlineKeyboardMarkup:
    # ROW 1: [ 🔍 بحث ] | [ 🎲 إقترح لي ]
    # ROW 2: [ ⭐ قائمة المفضلة ]
    # ROW 3: [ 🛠️ الدعم الفني ] | [ ❓ مساعدة ]
    # ROW 4: [ 📢 للإعلانات والتمويل ]
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
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

async def send_welcome_panel(message: Message):
    welcome_text = (
        "✨ <b>أهلاً بك في بوت أنمي وانمي | Anime & Anmie</b> 🎬\n\n"
        "مرحباً بك في وجهتك الأولى لمشاهدة وتحميل الأنمي بجودة عالية وسرعة فائقة! 🚀\n"
        "البوت يدعم البحث الذكي (بالعربية والإنجليزية وأسماء الشخصيات) وتنزيل الحلقات مباشرة داخل تلغرام بأحجام تصل إلى 2 جيجابايت.\n\n"
        "👇 <b>اختر من القائمة أدناه لبدء المغامرة:</b>"
    )
    await message.answer(welcome_text, reply_markup=get_welcome_markup(), parse_mode="HTML")

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
                from app.database.models import DownloadCache
                
                stmt = select(DownloadCache).where(DownloadCache.id == cache_id)
                res = await db_session.execute(stmt)
                dl_cache = res.scalar_one_or_none()
                
                if dl_cache:
                    await state.clear()
                    keyboard_buttons = [
                        [InlineKeyboardButton(text="⭐ تلقائي (حجم ذكي <= 2 جيجابايت)", callback_data=f"dl:auto:{dl_cache.id}")]
                    ]
                    quality_row = []
                    for q in ["1080p", "720p", "480p", "360p"]:
                        if q in dl_cache.qualities:
                            quality_row.append(InlineKeyboardButton(text=q, callback_data=f"dl:{q}:{dl_cache.id}"))
                    if quality_row:
                        keyboard_buttons.append(quality_row)
                        
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

    await send_welcome_panel(message)

@router.message(Command("help"))
async def cmd_help(message: Message):
    """Handles the /help command."""
    help_text = (
        "ℹ️ <b>تعليمات استخدام البوت</b>:\n\n"
        "1. <b>البحث</b>: أرسل اسم الأنمي باللغة العربية أو الإنجليزية أو اسم الشخصية.\n"
        "2. <b>الاختيار</b>: اختر الأنمي المناسب من قائمة نتائج البحث المعروضة.\n"
        "3. <b>تحديد الحلقة</b>: اكتب رقم الحلقة التي ترغب بتحميلها.\n"
        "4. <b>الجودة</b>: اختر الجودة المفضلة أو اختر 'تلقائي' ليقوم البوت بضبط جودة الفيديو تلقائياً لتناسب حجم الرفع.\n\n"
        "⚙️ <i>ملاحظة: يدعم البوت تحميل ملفات الأنمي الكبيرة حتى 2 جيجابايت لتجربة متكاملة.</i>"
    )
    await message.answer(help_text, parse_mode="HTML")

@router.callback_query(F.data == "check_sub")
async def handle_check_subscription(callback: CallbackQuery):
    bot = callback.bot
    user_id = callback.from_user.id
    
    if not config.CHANNEL_USERNAME:
        await callback.answer("تم التحقق بنجاح! البوت مفعل للجميع.")
        try:
            await callback.bot.delete_message(chat_id=callback.message.chat.id, message_id=callback.message.message_id)
        except Exception:
            pass
        await send_welcome_panel(callback.message)
        return
        
    try:
        member = await bot.get_chat_member(chat_id=config.CHANNEL_USERNAME, user_id=user_id)
        if member.status in ("member", "administrator", "creator"):
            await callback.answer("✅ تم التحقق بنجاح! شكراً لاشتراكك.", show_alert=True)
            try:
                await callback.bot.delete_message(chat_id=callback.message.chat.id, message_id=callback.message.message_id)
            except Exception:
                pass
            await send_welcome_panel(callback.message)
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
        await send_welcome_panel(callback.message)

@router.callback_query(F.data == "menu_search")
async def handle_menu_search(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer("🔍 **أرسل اسم الأنمي الذي تريد البحث عنه الآن (بالعربية أو الإنجليزية):**")

@router.callback_query(F.data == "menu_suggest")
async def handle_menu_suggest(callback: CallbackQuery):
    await callback.answer()
    suggested = random.choice(SUGGESTIONS)
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🔍 ابحث عن {suggested}", callback_data=f"suggest_search:{suggested}")]
    ])
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
    
    if not favs:
        await callback.message.answer("⭐ <b>قائمة المفضلة فارغة حالياً.</b>\nيمكنك إضافة أي أنمي للمفضلة عند البحث عنه وعرض تفاصيله!", parse_mode="HTML")
        return
        
    text = "⭐ <b>قائمة الأنميات المفضلة لديك:</b>\n\n"
    buttons = []
    for f in favs:
        buttons.append([InlineKeyboardButton(text=f.anime_title, callback_data=f"suggest_search:{f.anime_title}")])
        
    markup = InlineKeyboardMarkup(inline_keyboard=buttons)
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
    await callback.message.answer(support_text, parse_mode="HTML")

@router.callback_query(F.data == "menu_help")
async def handle_menu_help(callback: CallbackQuery):
    await callback.answer()
    help_text = (
        "ℹ️ <b>تعليمات استخدام البوت</b>:\n\n"
        "1. <b>البحث</b>: أرسل اسم الأنمي باللغة العربية أو الإنجليزية أو اسم الشخصية.\n"
        "2. <b>الاختيار</b>: اختر الأنمي المناسب من قائمة نتائج البحث المعروضة.\n"
        "3. <b>تحديد الحلقة</b>: اكتب رقم الحلقة التي ترغب بتحميلها.\n"
        "4. <b>الجودة</b>: اختر الجودة المفضلة أو اختر 'تلقائي' ليقوم البوت بضبط جودة الفيديو تلقائياً لتناسب حجم الرفع.\n\n"
        "⚙️ <i>ملاحظة: يدعم البوت تحميل ملفات الأنمي الكبيرة حتى 2 جيجابايت لتجربة متكاملة.</i>"
    )
    await callback.message.answer(help_text, parse_mode="HTML")

@router.callback_query(F.data == "menu_ads")
async def handle_menu_ads(callback: CallbackQuery):
    await callback.answer()
    ads_text = (
        "📢 <b>للإعلانات والتمويل والتبرع:</b>\n\n"
        "لدعم استمرار خوادم البوت وتطويره، أو لطلب مساحات إعلانية داخل البوت والقناة، يرجى التواصل مع الإدارة:\n"
        "👉 @botanmie_admin\n\n"
        "رأيكم ودعمكم يهمنا! 🌟"
    )
    await callback.message.answer(ads_text, parse_mode="HTML")
