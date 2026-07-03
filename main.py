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
from app.handlers import start, search, download, admin
from app.utils.logging_config import logger

async def main():
    # 1. Validate environment variables configuration
    try:
        config.validate()
    except ValueError as e:
        logger.error(f"Configuration Error: {e}")
        sys.exit(1)

    # 1.5. Test Proxy Connectivity if configured
    if config.PROXY_URL:
        logger.info("Testing proxy connectivity...")
        try:
            from aiohttp_socks import ProxyConnector
            import aiohttp
            connector = ProxyConnector.from_url(config.PROXY_URL)
            async with aiohttp.ClientSession(connector=connector) as test_session:
                async with test_session.get("https://graphql.anilist.co", timeout=5) as test_resp:
                    logger.info(f"Proxy connectivity check succeeded with status {test_resp.status}!")
        except Exception as e:
            logger.warning(
                f"SOCKS5 proxy health check failed: {e}. "
                "Disabling proxy and falling back to direct connections."
            )
            config.PROXY_URL = None

    # 2. Boot and migrate Database schema
    logger.info("Initializing database schema...")
    await init_db()

    # 3. Setup Custom Bot Session (Local Bot API server support for files up to 2GB)
    session = None
    if config.TELEGRAM_API_SERVER:
        try:
            logger.info(f"Connecting using custom local Bot API server: {config.TELEGRAM_API_SERVER}")
            api_server = TelegramAPIServer.from_base(config.TELEGRAM_API_SERVER)
            session = AiohttpSession(api=api_server)
        except Exception:
            logger.exception("Error creating custom Bot API session. Falling back to default.")
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
    dp.include_router(admin.router)
    dp.include_router(start.router)
    dp.include_router(search.router)
    dp.include_router(download.router)

    # 7. Start polling
    logger.info("Bot polling started.")
    try:
        await dp.start_polling(bot)
    except Exception:
        logger.exception("Fatal error in bot polling loop")
    finally:
        await bot.session.close()
        logger.info("Bot session closed.")

if __name__ == "__main__":
    # Handle Windows SelectorEventLoop policy issues with Asyncio
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped by user interrupt.")
