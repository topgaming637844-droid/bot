import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)

# Enforce a fixed writeable directory for Playwright browser binaries on Linux/production
if os.name != "nt":
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "/app/playwright-browsers"


class Config:
    BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///bot.db").strip()
    TELEGRAM_API_SERVER = os.getenv("TELEGRAM_API_SERVER", "").strip() or None
    PROXY_URL = os.getenv("PROXY_URL", "").strip() or None
    SUPER_ADMIN_ID = int(os.getenv("SUPER_ADMIN_ID", "0").strip())
    CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME", "").strip() or None
    
    # Latest Release Notifier Toggle
    ENABLE_LATEST_NOTIFIER = os.getenv("ENABLE_LATEST_NOTIFIER", "True").strip().lower() in ("true", "1", "yes", "on")
    NOTIFICATION_DELAY_MINUTES = int(os.getenv("NOTIFICATION_DELAY_MINUTES", "5").strip())

    # Parse MOCK_MODE boolean
    mock_mode_str = os.getenv("MOCK_MODE", "True").strip().lower()
    MOCK_MODE = mock_mode_str in ("true", "1", "yes", "on")

    # FastAPI Webhook and Library Configuration
    WEBHOOK_URL = os.getenv("WEBHOOK_URL", "").strip() or None
    LIBRARY_GROUP_ID = int(os.getenv("LIBRARY_GROUP_ID", "-1003757034229").strip())
    
    # Telegram Mini App Base URL (strictly enforce HTTPS for Telegram compatibility)
    webapp_env = os.getenv("WEBAPP_BASE_URL", "").strip()
    if webapp_env:
        domain = webapp_env
    else:
        domain = (
            os.getenv("RAILWAY_PUBLIC_DOMAIN", "").strip()
            or os.getenv("RAILWAY_STATIC_URL", "").strip()
            or os.getenv("RAILWAY_SERVICE_DOMAIN", "").strip()
        )
    
    if domain:
        # Standardize by removing existing protocol prefixes
        if domain.startswith("http://"):
            domain = domain[7:]
        elif domain.startswith("https://"):
            domain = domain[8:]
        WEBAPP_BASE_URL = f"https://{domain}"
    else:
        WEBAPP_BASE_URL = "https://botanmie.up.railway.app"

    # Static list of 10 modern organic browser User-Agents for dynamic header rotation
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/605.1.15",
        "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (iPad; CPU OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/605.1.15",
        "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Mobile Safari/537.36"
    ]

    # Target directory for temporary downloads
    DOWNLOAD_DIR = Path(__file__).parent / "downloads"
    DOWNLOAD_DIR.mkdir(exist_ok=True)

    @classmethod
    def validate(cls):
        """Validates critical settings on startup."""
        if not cls.BOT_TOKEN or cls.BOT_TOKEN == "place_your_bot_token_here":
            raise ValueError("BOT_TOKEN is not configured! Please set it in your .env file.")
        
        # Log active settings (mask token for security)
        masked_token = cls.BOT_TOKEN[:8] + "..." + cls.BOT_TOKEN[-8:] if len(cls.BOT_TOKEN) > 16 else "invalid"
        print("--- CONFIGURATION LOADED ---")
        print(f"Bot Token: {masked_token}")
        print(f"Database URL: {cls.DATABASE_URL}")
        print(f"Proxy URL: {cls.PROXY_URL or 'None'}")
        print(f"Mock Mode: {cls.MOCK_MODE}")
        print(f"Super Admin ID: {cls.SUPER_ADMIN_ID}")
        print(f"Channel Username: {cls.CHANNEL_USERNAME or 'None'}")
        print(f"Telegram API Server: {cls.TELEGRAM_API_SERVER or 'Default (Official)'}")
        print(f"WebApp Base URL: {cls.WEBAPP_BASE_URL}")
        
        # Debug env variables
        print("--- DEBUG RAILWAY ENVIRONMENT ---")
        for k, v in sorted(os.environ.items()):
            if k.startswith("RAILWAY_") or k in ("PORT", "WEBAPP_BASE_URL"):
                if "token" in k.lower() or "secret" in k.lower() or "password" in k.lower() or "database_url" in k.lower():
                    v = "***"
                print(f"{k}: {v}")
        print("---------------------------------")
        print("----------------------------")

# Create a global config instance
config = Config
