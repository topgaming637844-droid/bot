from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from sqlalchemy import select
from app.database.models import Blacklist
from app.utils.logging_config import logger

class BlacklistMiddleware(BaseMiddleware):
    """Middleware to block blacklisted user IDs instantly across all interactions."""
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
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

        db_session = data.get("db_session")
        if db_session:
            try:
                stmt = select(Blacklist).where(Blacklist.user_id == user.id)
                res = await db_session.execute(stmt)
                blacklisted = res.scalar_one_or_none()
                if blacklisted:
                    logger.warning(f"Blocked request from blacklisted user_id={user.id}")
                    if isinstance(inner_event, CallbackQuery):
                        try:
                            await inner_event.answer("🚫 تم حظر حسابك من استخدام هذا البوت.", show_alert=True)
                        except Exception:
                            pass
                    return  # Drop request, don't execute handler
            except Exception as e:
                logger.exception("Error checking blacklist middleware")
                try:
                    await db_session.rollback()
                except Exception:
                    pass

        return await handler(event, data)
