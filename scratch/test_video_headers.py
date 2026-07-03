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

async def test_dl_link(url: str):
    print(f"\nRequesting direct link: {url}...")
    headers = {"User-Agent": get_random_user_agent()}
    connector = get_connector()
    async with aiohttp.ClientSession(connector=connector) as session:
        try:
            async with session.head(url, headers=headers, allow_redirects=True, timeout=10) as response:
                print(f"  HEAD response status: {response.status}")
                print(f"  HEAD response headers: {dict(response.headers)}")
                
                # If HEAD fails or returns text, let's do a GET with a short range or just check headers
                if "text/html" in response.headers.get("Content-Type", ""):
                    print("  [WARNING] HEAD returned HTML. Trying GET...")
                    async with session.get(url, headers=headers, allow_redirects=True, timeout=10) as get_resp:
                        print(f"    GET response status: {get_resp.status}")
                        print(f"    GET response headers: {dict(get_resp.headers)}")
        except Exception as e:
            print(f"  Failed: {e}")

async def main():
    # Test otakuvid.online download link
    await test_dl_link("https://otakuvid.online/download/upzfvdqh0kxy_n")

if __name__ == "__main__":
    asyncio.run(main())
