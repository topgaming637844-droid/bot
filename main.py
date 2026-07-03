import asyncio
import sys
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.enums import ParseMode

from config import config
from app.database.connection import init_db
from app.middlewares.db_session import DbSessionMiddleware
from app.handlers import start, search, download

async def main():
    # 1. Validate environment variables configuration
    try:
        config.validate()
    except ValueError as e:
        print(f"Configuration Error: {e}", file=sys.stderr)
        sys.exit(1)

    # 2. Boot and migrate Database schema
    await init_db()

    # 3. Setup Custom Bot Session (Local Bot API server support for files up to 2GB)
    session = None
    if config.TELEGRAM_API_SERVER:
        try:
            print(f"Connecting using custom local Bot API server: {config.TELEGRAM_API_SERVER}")
            api_server = TelegramAPIServer.from_base(config.TELEGRAM_API_SERVER)
            session = AiohttpSession(api_server=api_server)
        except Exception as e:
            print(f"Error creating custom Bot API session: {e}. Falling back to default.")
            session = None

    # 4. Initialize Bot and Dispatcher instances
    bot = Bot(
        token=config.BOT_TOKEN,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    
    # Using memory storage for Finite State Machine (FSM)
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    # 5. Bind Database Middleware to inject session to handlers
    dp.update.outer_middleware(DbSessionMiddleware())

    # 6. Register Handler Routers
    dp.include_router(start.router)
    dp.include_router(search.router)
    dp.include_router(download.router)

    # 7. Start polling
    print("Bot polling started. Press Ctrl+C to exit.")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    # Handle Windows SelectorEventLoop policy issues with Asyncio
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Bot stopped.")
