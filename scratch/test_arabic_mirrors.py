import asyncio
import aiohttp
import sys
from pathlib import Path

# Add project root to path
project_root = Path("c:/Users/monsm/OneDrive/Desktop/BOT")
sys.path.append(str(project_root))

from config import config
from app.utils.user_agents import get_random_user_agent
from app.services.anilist import get_connector

async def test_site(url: str):
    print(f"Testing access to: {url}...")
    headers = {"User-Agent": get_random_user_agent()}
    connector = get_connector()
    async with aiohttp.ClientSession(connector=connector) as session:
        try:
            async with session.get(url, headers=headers, timeout=10) as response:
                print(f"  Status: {response.status}")
                print(f"  Headers: {dict(response.headers)}")
                body = await response.read()
                print(f"  Response starts with: {body[:300]}")
        except Exception as e:
            print(f"  Error accessing {url}: {e}")

async def main():
    # Test witanime
    await test_site("https://witanime.pics/")
    print("-" * 50)
    # Test anime4up
    await test_site("https://anime4up.to/")

if __name__ == "__main__":
    asyncio.run(main())
