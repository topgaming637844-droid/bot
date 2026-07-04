import asyncio
import sys
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
import uvicorn

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.enums import ParseMode
from aiogram.types import Update

from config import config
from app.database.connection import init_db, AsyncSessionLocal
from app.middlewares.db_session import DbSessionMiddleware
from app.handlers import start, search, download, admin
from app.utils.logging_config import logger
from app.services.worker import recover_stuck_tasks, task_consumer_worker

# Global bot and dispatcher placeholders
bot: Bot = None
dp: Dispatcher = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Validate configuration
    try:
        config.validate()
    except ValueError as e:
        logger.error(f"Configuration Error: {e}")
        sys.exit(1)

    # 1.5. Test Proxy Connectivity
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

    # 2. Initialize Database and recover stuck tasks
    logger.info("Initializing database schema...")
    await init_db()
    
    logger.info("Recovering stuck tasks on boot...")
    await recover_stuck_tasks(AsyncSessionLocal)

    # 3. Setup Bot Session
    bot_timeout = 600
    session = None
    if config.TELEGRAM_API_SERVER:
        try:
            logger.info(f"Connecting using custom local Bot API server: {config.TELEGRAM_API_SERVER}")
            api_server = TelegramAPIServer.from_base(config.TELEGRAM_API_SERVER)
            session = AiohttpSession(api=api_server, timeout=bot_timeout)
        except Exception:
            logger.exception("Error creating custom Bot API session. Falling back to default.")
            session = None
    if session is None:
        session = AiohttpSession(timeout=bot_timeout)

    # 4. Initialize Bot and Dispatcher
    global bot, dp
    bot = Bot(
        token=config.BOT_TOKEN,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    # 5. Bind Middlewares
    from app.middlewares.subscription import SubscriptionMiddleware
    dp.update.outer_middleware(DbSessionMiddleware())
    dp.update.outer_middleware(SubscriptionMiddleware())

    # 6. Register routers
    dp.include_router(admin.router)
    dp.include_router(start.router)
    dp.include_router(search.router)
    dp.include_router(download.router)

    # 7. Configure Telegram Webhook
    webhook_url = config.WEBHOOK_URL
    if not webhook_url and os.getenv("RAILWAY_PUBLIC_DOMAIN"):
        domain = os.getenv("RAILWAY_PUBLIC_DOMAIN")
        if not domain.startswith("http"):
            webhook_url = f"https://{domain}/webhook"
        else:
            webhook_url = f"{domain}/webhook"

    if webhook_url:
        logger.info(f"Setting webhook dynamically to: {webhook_url}")
        await bot.set_webhook(webhook_url, drop_pending_updates=True)
    else:
        logger.warning("WEBHOOK_URL is not set. Webhook was not registered dynamically.")

    # 8. Start Background Async Consumer Loop
    asyncio.create_task(task_consumer_worker(bot, AsyncSessionLocal))

    yield

    # Shutdown
    if bot:
        await bot.session.close()
    logger.info("Bot session closed successfully.")

# Initialize FastAPI App
app = FastAPI(lifespan=lifespan)

@app.post("/webhook")
async def webhook_endpoint(request: Request):
    if not bot or not dp:
        return {"status": "not_initialized"}
    update_data = await request.json()
    update = Update.model_validate(update_data, context={"bot": bot})
    await dp.feed_update(bot, update)
    return {"status": "ok"}

@app.get("/health")
async def health_check():
    return {"status": "ok", "timestamp": time.time()}

if __name__ == "__main__":
    # Handle Windows SelectorEventLoop policy issues
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    port = int(os.getenv("PORT", "8080"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, loop="asyncio")
