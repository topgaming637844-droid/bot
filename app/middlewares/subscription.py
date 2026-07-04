from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from config import config
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

class SubscriptionMiddleware(BaseMiddleware):
    """Middleware to enforce channel subscription before accessing bot features."""
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        # Check if CHANNEL_USERNAME is configured
        if not config.CHANNEL_USERNAME:
            return await handler(event, data)
            
        # Extract user
        user = None
        if isinstance(event, Message):
            user = event.from_user
            # Allow /start command to pass through
            if event.text and event.text.startswith("/start"):
                return await handler(event, data)
        elif isinstance(event, CallbackQuery):
            user = event.from_user
            # Allow verification and menu callback to pass through
            if event.data == "check_sub" or event.data.startswith("menu_"):
                return await handler(event, data)
                
        if not user:
            return await handler(event, data)
            
        # Super admin bypass
        if user.id == config.SUPER_ADMIN_ID:
            return await handler(event, data)
            
        # Admin bypass (check from bot_admins db table)
        db_session = data.get("db_session")
        if db_session:
            try:
                from sqlalchemy import select
                from app.database.models import BotAdmin
                stmt = select(BotAdmin).where(BotAdmin.user_id == user.id)
                res = await db_session.execute(stmt)
                is_db_admin = res.scalar_one_or_none() is not None
                if is_db_admin:
                    return await handler(event, data)
            except Exception:
                pass
                
        # Perform member check in the channel
        bot = data["bot"]
        try:
            member = await bot.get_chat_member(chat_id=config.CHANNEL_USERNAME, user_id=user.id)
            if member.status in ("member", "administrator", "creator"):
                return await handler(event, data)
        except Exception as e:
            # If checking fails (e.g. bot not in channel), do not block the user to avoid complete outages
            from app.utils.logging_config import logger
            logger.warning(f"Failed to check channel membership for user {user.id} in {config.CHANNEL_USERNAME}: {e}")
            return await handler(event, data)
            
        # If user is not member, restrict access and prompt to join
        channel_link = f"https://t.me/{config.CHANNEL_USERNAME.lstrip('@')}"
        text = (
            f"⚠️ <b>عذراً، يجب عليك الاشتراك في القناة أولاً لتتمكن من استخدام البوت!</b>\n\n"
            f"يرجى الانضمام إلى القناة الرسمية أدناه، ثم اضغط على زر التحقق 👇"
        )
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 اشترك في القناة الرسمية", url=channel_link)],
            [InlineKeyboardButton(text="✅ تحقق من الاشتراك", callback_data="check_sub")]
        ])
        
        if isinstance(event, Message):
            await event.answer(text, reply_markup=markup, parse_mode="HTML")
        elif isinstance(event, CallbackQuery):
            try:
                await event.message.answer(text, reply_markup=markup, parse_mode="HTML")
            except Exception:
                pass
            await event.answer("⚠️ يجب عليك الاشتراك أولاً لاستخدام البوت!", show_alert=True)
            
        return None
