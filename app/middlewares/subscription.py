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
        # Extract inner event and user from Update wrapper if present
        from aiogram.types import Update
        inner_event = event
        user = None
        
        if isinstance(event, Update):
            if event.message:
                inner_event = event.message
                user = event.message.from_user
            elif event.callback_query:
                inner_event = event.callback_query
                user = event.callback_query.from_user
        else:
            user = event.from_user if hasattr(event, "from_user") else None
            
        if not user:
            return await handler(event, data)

        bot = data["bot"]
        db_session = data.get("db_session")

        # 1. Register/Update User and Notify Admins on first interaction
        if db_session:
            try:
                from app.database.models import User
                from sqlalchemy import select
                stmt_user = select(User).where(User.user_id == user.id)
                res_user = await db_session.execute(stmt_user)
                existing_user = res_user.scalar_one_or_none()
                if not existing_user:
                    new_user = User(
                        user_id=user.id,
                        username=user.username,
                        first_name=user.first_name,
                        last_name=user.last_name,
                        is_blocked=False
                    )
                    db_session.add(new_user)
                    await db_session.commit()
                    from app.utils.logging_config import logger
                    logger.info(f"Registered new user in database from middleware: {user.id}")
                    
                    # Notify admins
                    try:
                        from app.database.models import BotAdmin
                        stmt_admins = select(BotAdmin.user_id)
                        res_admins = await db_session.execute(stmt_admins)
                        admin_ids = list(res_admins.scalars().all())
                        admin_ids.append(config.SUPER_ADMIN_ID)
                        admin_ids = list(set(admin_ids))
                        
                        name_str = f"{user.first_name or ''} {user.last_name or ''}".strip() or "لا يوجد اسم"
                        user_link = f"<a href='tg://user?id={user.id}'>{name_str}</a>"
                        notif_text = (
                            f"👤 <b>مستخدم جديد دخل البوت! | New User Joined</b>\n\n"
                            f"• <b>الاسم:</b> {user_link}\n"
                            f"• <b>المعرف (ID):</b> <code>{user.id}</code>\n"
                            f"• <b>اليوزر نيم:</b> @{user.username or 'لا يوجد'}"
                        )
                        for admin_id in admin_ids:
                            try:
                                await bot.send_message(chat_id=admin_id, text=notif_text, parse_mode="HTML")
                            except Exception:
                                pass
                    except Exception:
                        pass
                else:
                    existing_user.username = user.username
                    existing_user.first_name = user.first_name
                    existing_user.last_name = user.last_name
                    existing_user.is_blocked = False
                    db_session.add(existing_user)
                    await db_session.commit()
            except Exception:
                pass

        # Check if CHANNEL_USERNAME is configured
        if not config.CHANNEL_USERNAME:
            return await handler(event, data)

        # Allow verification callback to pass through
        if isinstance(inner_event, CallbackQuery) and inner_event.data == "check_sub":
            return await handler(event, data)

        # Check membership in the channel
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
        
        if isinstance(inner_event, Message):
            await inner_event.answer(text, reply_markup=markup, parse_mode="HTML")
        elif isinstance(inner_event, CallbackQuery):
            try:
                await inner_event.message.answer(text, reply_markup=markup, parse_mode="HTML")
            except Exception:
                pass
            await inner_event.answer("⚠️ يجب عليك الاشتراك أولاً لاستخدام البوت!", show_alert=True)
            
        return None
