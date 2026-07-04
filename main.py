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

async def restore_persistent_settings(bot: Bot):
    from app.utils.settings import get_setting
    from config import config
    from pathlib import Path
    import aiohttp
    
    # 1. Restore Channel Username
    saved_channel = await get_setting("channel_username")
    if saved_channel:
        config.CHANNEL_USERNAME = saved_channel
        logger.info(f"Restored channel username from database: {saved_channel}")
        
    # 2. Restore Custom Thumbnail Photo
    thumb_file_id = await get_setting("custom_thumb_file_id")
    thumb_url = await get_setting("custom_thumb_url")
    
    if thumb_file_id or thumb_url:
        data_dir = Path(__file__).parent / "app" / "data"
        data_dir.mkdir(exist_ok=True, parents=True)
        thumb_path = data_dir / "custom_thumb.jpg"
        thumb_id_path = data_dir / "custom_thumb_id.txt"
        
        if thumb_file_id:
            try:
                with open(thumb_id_path, "w") as f_id:
                    f_id.write(thumb_file_id)
            except Exception as e:
                logger.warning(f"Failed to write file ID to custom_thumb_id.txt: {e}")
            
        if not thumb_path.exists():
            if thumb_file_id:
                logger.info(f"Local thumbnail missing on boot. Restoring file ID: {thumb_file_id}")
                try:
                    get_file_url = f"https://api.telegram.org/bot{config.BOT_TOKEN}/getFile?file_id={thumb_file_id}"
                    async with aiohttp.ClientSession() as session:
                        async with session.get(get_file_url, ssl=False, timeout=15) as resp:
                            if resp.status == 200:
                                res_json = await resp.json()
                                if res_json.get("ok"):
                                    file_path = res_json["result"]["file_path"]
                                    download_url = f"https://api.telegram.org/file/bot{config.BOT_TOKEN}/{file_path}"
                                    async with session.get(download_url, ssl=False, timeout=30) as img_resp:
                                        if img_resp.status == 200:
                                            image_bytes = await img_resp.read()
                                            with open(thumb_path, "wb") as f:
                                                f.write(image_bytes)
                                            logger.info("Custom background thumbnail successfully restored on boot.")
                                        else:
                                            logger.error(f"Failed to download thumbnail bytes, HTTP status: {img_resp.status}")
                                else:
                                    logger.error(f"Telegram getFile returned error response: {res_json}")
                            else:
                                logger.error(f"Telegram getFile request failed, HTTP status: {resp.status}")
                except Exception as e:
                    logger.exception(f"Failed to restore background thumbnail on boot: {e}")
            elif thumb_url:
                logger.info(f"Local thumbnail missing on boot. Restoring from URL: {thumb_url}")
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(thumb_url, ssl=False, timeout=30) as resp:
                            if resp.status == 200:
                                image_bytes = await resp.read()
                                with open(thumb_path, "wb") as f:
                                    f.write(image_bytes)
                                logger.info("Custom background thumbnail successfully restored from URL on boot.")
                            else:
                                logger.error(f"Failed to fetch thumbnail from URL, HTTP status: {resp.status}")
                except Exception as e:
                    logger.exception(f"Failed to restore background thumbnail from URL on boot: {e}")

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

    # 4.5. Restore Settings
    logger.info("Restoring system settings from database...")
    await restore_persistent_settings(bot)

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
        logger.warning("WEBHOOK_URL is not set. Webhook was not registered dynamically. Falling back to Long Polling in background...")
        try:
            await bot.delete_webhook(drop_pending_updates=True)
        except Exception:
            logger.exception("Failed to delete webhook on startup")
        asyncio.create_task(dp.start_polling(bot, handle_signals=False))

    # 8. Start Background Async Consumer Loop
    asyncio.create_task(task_consumer_worker(bot, AsyncSessionLocal))

    yield

    # Shutdown
    if bot:
        await bot.session.close()
    logger.info("Bot session closed successfully.")

# Initialize FastAPI App
app = FastAPI(lifespan=lifespan)

from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import select
from app.database.models import SearchCache, EpisodeCache, DownloadCache

class WebAppEpisodePayload(BaseModel):
    init_data: str
    user_id: int
    anilist_id: int
    ep_number: str

class WebAppQualityPayload(BaseModel):
    init_data: str
    user_id: int
    db_cache_id: int
    anilist_id: int
    ep_number: str
    quality: str

@app.get("/webapp/episodes", response_class=HTMLResponse)
async def webapp_episodes(anilist_id: int):
    # Load episodes list from DB
    async with AsyncSessionLocal() as db_session:
        stmt = select(EpisodeCache).where(EpisodeCache.anilist_id == anilist_id)
        res = await db_session.execute(stmt)
        episodes = res.scalars().all()
        
        # Parse episodes using custom float sort to keep it in order
        from app.handlers.search import parse_ep_num
        episodes.sort(key=lambda x: parse_ep_num(x.ep_number))
        
        # Load HTML template file
        # عدل مسار الملف عشان يشاور صح على templates
        template_path = os.path.join(os.path.dirname(__file__), "templates", "episodes.html")

        with open(template_path, "r", encoding="utf-8") as f:
            html_content = f.read()

        # هنا بقى التريكة، لازم نبعت الـ content للـ HTMLResponse
        return HTMLResponse(content=html_content, status_code=200)
            
        # Perform dynamic template replacement
        buttons_html = ""
        for ep in episodes:
            buttons_html += f'<button class="btn" onclick="selectEpisode(\'{ep.ep_number}\')">{ep.ep_number}</button>\n'
            
        content = content.replace('{{ anilist_id }}', str(anilist_id))
        
        # Replace the Jinja block with our pre-built HTML
        start_jinja = content.find('{% for ep in episodes %}')
        end_jinja = content.find('{% endfor %}') + len('{% endfor %}')
        if start_jinja != -1 and end_jinja != -1:
            content = content[:start_jinja] + buttons_html + content[end_jinja:]
            
        return content

@app.get("/webapp/qualities", response_class=HTMLResponse)
async def webapp_qualities(db_cache_id: int, anilist_id: int, ep_number: str):
    async with AsyncSessionLocal() as db_session:
        stmt = select(DownloadCache).where(DownloadCache.id == db_cache_id)
        res = await db_session.execute(stmt)
        dl_cache = res.scalar_one_or_none()
        
        qualities = dl_cache.qualities if dl_cache else {}
        
        template_path = os.path.join(os.path.dirname(__file__), "app", "templates", "qualities.html")
        with open(template_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        # Build quality buttons HTML dynamically
        buttons_html = ""
        if "auto" in qualities or not qualities:
            buttons_html += '<button class="btn btn-auto" onclick="selectQuality(\'auto\')">تلقائي (حجم ذكي &lt;= 2 جيجا)</button>\n'
        for q in ["1080p", "720p", "480p", "360p"]:
            if q in qualities:
                btn_class = f"btn-{q}"
                buttons_html += f'<button class="btn {btn_class}" onclick="selectQuality(\'{q}\')">{q}</button>\n'
                
        content = content.replace('{{ db_cache_id }}', str(db_cache_id))
        content = content.replace('{{ anilist_id }}', str(anilist_id))
        content = content.replace('{{ ep_number }}', str(ep_number))
        
        # Replace Jinja if blocks with our pre-built HTML
        start_list = content.find('<div class="list" id="list">') + len('<div class="list" id="list">')
        end_list = content.find('</div>', start_list)
        if start_list != -1 and end_list != -1:
            content = content[:start_list] + "\n" + buttons_html + content[end_list:]
            
        return content

@app.post("/api/webapp/select_episode")
async def api_select_episode(payload: WebAppEpisodePayload):
    logger.info(f"WebApp api_select_episode payload: {payload}")
    
    async with AsyncSessionLocal() as db_session:
        stmt = select(EpisodeCache).where(
            (EpisodeCache.anilist_id == payload.anilist_id) & (EpisodeCache.ep_number == payload.ep_number)
        )
        res = await db_session.execute(stmt)
        ep_entry = res.scalar_one_or_none()
        
        if not ep_entry:
            return {"status": "error", "message": "Episode not found"}
            
        stmt_s = select(SearchCache).where(SearchCache.anilist_id == payload.anilist_id)
        res_s = await db_session.execute(stmt_s)
        cache_entry = res_s.scalars().first()
        title = cache_entry.title_english or cache_entry.title_romaji if cache_entry else "أنمي"
        if title.startswith("WITANIME:"):
            title = cache_entry.title_english
            
        duration = cache_entry.duration if cache_entry else None
        
        # Trigger quality prompt in Telegram chat
        from app.handlers.download import prompt_quality_selection
        await prompt_quality_selection(
            bot=bot,
            chat_id=payload.user_id,
            anilist_id=payload.anilist_id,
            ep_number=payload.ep_number,
            play_url=ep_entry.play_url,
            anime_title=title,
            duration=duration,
            db_session=db_session
        )
        
    return {"status": "ok"}

@app.post("/api/webapp/select_quality")
async def api_select_quality(payload: WebAppQualityPayload):
    logger.info(f"WebApp api_select_quality payload: {payload}")
    
    async with AsyncSessionLocal() as db_session:
        stmt_s = select(SearchCache).where(SearchCache.anilist_id == payload.anilist_id)
        res_s = await db_session.execute(stmt_s)
        cache_entry = res_s.scalars().first()
        title = cache_entry.title_english or cache_entry.title_romaji if cache_entry else "أنمي"
        if title.startswith("WITANIME:"):
            title = cache_entry.title_english
            
        # Create enqueued status message
        status_msg = await bot.send_message(
            chat_id=payload.user_id,
            text=(
                f"⏳ **تم إضافة طلبك لقائمة الانتظار:**\n"
                f"🎬 الأنمي: {title}\n"
                f"🔢 الحلقة: {payload.ep_number}\n"
                f"⚙️ الجودة: {payload.quality}\n\n"
                f"🔄 جاري بدء المعالجة والتحميل، يرجى الانتظار..."
            ),
            parse_mode="Markdown"
        )
        
        from app.database.models import PersistentTaskQueue
        new_task = PersistentTaskQueue(
            user_id=payload.user_id,
            chat_id=payload.user_id,
            message_id=status_msg.message_id,
            anilist_id=payload.anilist_id,
            anime_title=title,
            episode_num=payload.ep_number,
            quality=payload.quality,
            status="pending"
        )
        db_session.add(new_task)
        await db_session.commit()
        logger.info(f"Enqueued WebApp download task {new_task.id} for User {payload.user_id}")
        
    return {"status": "ok"}

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
