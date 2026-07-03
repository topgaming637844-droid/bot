from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from app.database.connection import AsyncSessionLocal

class DbSessionMiddleware(BaseMiddleware):
    """Middleware to inject SQLAlchemy AsyncSession into handler handlers."""
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        async with AsyncSessionLocal() as session:
            data["db_session"] = session
            return await handler(event, data)
            # Session automatically commits/rolls back and closes when exiting block
