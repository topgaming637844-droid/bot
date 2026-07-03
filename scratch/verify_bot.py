import asyncio
import sys
from pathlib import Path
from sqlalchemy import select

# Reconfigure stdout and stderr to handle Arabic characters in console outputs without UnicodeEncodeErrors
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

project_root = Path("c:/Users/monsm/OneDrive/Desktop/BOT")
sys.path.append(str(project_root))

from config import config
# Override database URL to a local sqlite database for local verification
config.DATABASE_URL = "sqlite+aiosqlite:///test_bot.db"

# Restore original PROXY_URL from environment for testing the health check fallback
import os
config.PROXY_URL = os.getenv("PROXY_URL", "").strip() or None

print(f"Configured DATABASE_URL override: {config.DATABASE_URL}")
print(f"Testing with PROXY_URL from .env: {config.PROXY_URL}")

from app.database.connection import init_db, AsyncSessionLocal
from app.database.models import BotAdmin
from app.utils.auth import is_admin
from app.services.scraper import get_episodes_scraper

async def run_proxy_check():
    if config.PROXY_URL:
        print("Testing proxy connectivity inside async loop...")
        try:
            from aiohttp_socks import ProxyConnector
            import aiohttp
            connector = ProxyConnector.from_url(config.PROXY_URL)
            async with aiohttp.ClientSession(connector=connector) as test_session:
                async with test_session.get("https://graphql.anilist.co", timeout=5) as test_resp:
                    print(f"Proxy connectivity check succeeded with status {test_resp.status}!")
        except Exception as e:
            print(f"SOCKS5 proxy health check failed: {e}. Disabling proxy and falling back to direct connections.")
            config.PROXY_URL = None

async def test_database():
    print("\n--- TESTING DATABASE INITIALIZATION ---")
    await init_db()
    
    print("\n--- TESTING BOTADMIN OPERATIONS ---")
    mock_user_id = 987654321
    mock_added_by = 123456789 # Super Admin ID from config.py/env
    
    # Configure config.SUPER_ADMIN_ID for testing
    config.SUPER_ADMIN_ID = 123456789
    print(f"Super Admin configured as: {config.SUPER_ADMIN_ID}")
    
    async with AsyncSessionLocal() as session:
        # Check if Super Admin is admin
        is_sa = await is_admin(123456789, session)
        print(f"Is Super Admin authorized? {is_sa} (Expected: True)")
        
        # Check if mock user is admin before adding
        is_mock_before = await is_admin(mock_user_id, session)
        print(f"Is Mock User authorized before adding? {is_mock_before} (Expected: False)")
        
        # Delete if already exists in DB
        stmt = select(BotAdmin).where(BotAdmin.user_id == mock_user_id)
        res = await session.execute(stmt)
        existing = res.scalar_one_or_none()
        if existing:
            await session.delete(existing)
            await session.commit()
            
        # Add mock user to BotAdmin table
        new_admin = BotAdmin(user_id=mock_user_id, added_by=mock_added_by)
        session.add(new_admin)
        await session.commit()
        print(f"Mock User {mock_user_id} added to BotAdmin table.")
        
        # Check if mock user is admin after adding
        is_mock_after = await is_admin(mock_user_id, session)
        print(f"Is Mock User authorized after adding? {is_mock_after} (Expected: True)")
        
        # Clean up mock admin
        stmt = select(BotAdmin).where(BotAdmin.user_id == mock_user_id)
        res = await session.execute(stmt)
        admin_entry = res.scalar_one_or_none()
        if admin_entry:
            await session.delete(admin_entry)
            await session.commit()
            print(f"Mock User {mock_user_id} removed from BotAdmin table.")
            
        is_mock_final = await is_admin(mock_user_id, session)
        print(f"Is Mock User authorized after cleanup? {is_mock_final} (Expected: False)")

async def test_scraper():
    print("\n--- TESTING PAGINATED EPISODES SCRAPER ---")
    slug = "one-piece"
    episodes = await get_episodes_scraper(slug)
    print(f"Successfully scraped and aggregated {len(episodes)} episodes.")
    if episodes:
        print(f"First episode play URL: {episodes[0]['play_url']}")
        print(f"Last episode play URL: {episodes[-1]['play_url']}")

async def main():
    try:
        await run_proxy_check()
        await test_database()
        await test_scraper()
        print("\nVerification completed successfully!")
    except Exception as e:
        print(f"\nVerification failed with error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
