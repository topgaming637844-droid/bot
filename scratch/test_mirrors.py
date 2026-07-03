import asyncio
import aiohttp
from bs4 import BeautifulSoup
import sys
from pathlib import Path

# Add project root to path
project_root = Path("c:/Users/monsm/OneDrive/Desktop/BOT")
sys.path.append(str(project_root))

from config import config
from app.utils.user_agents import get_random_user_agent
from app.services.anilist import get_connector

async def test_mirror(domain: str, session: aiohttp.ClientSession):
    print(f"\nTesting mirror: {domain}...")
    url = f"{domain}/search.html?keyword=Naruto"
    headers = {"User-Agent": get_random_user_agent()}
    try:
        async with session.get(url, headers=headers, timeout=10) as response:
            text = await response.text()
            print(f"  Status: {response.status} | Length: {len(text)} characters")
            
            soup = BeautifulSoup(text, "html.parser")
            page_title = soup.title.text.strip() if soup.title else "No Title"
            print(f"  Title: '{page_title}'")
            
            # Check for consent manager or Cloudflare
            if "Loading..." in page_title or "Just a moment" in page_title or len(text) < 1500:
                print("  [BLOCKED] Consent wall or JS challenge active.")
                return False
                
            items = soup.select("ul.items li")
            print(f"  [SUCCESS] Found {len(items)} items using selector 'ul.items li'")
            for i, item in enumerate(items[:2]):
                link_el = item.select_one("p.name a")
                if link_el:
                    print(f"    - {link_el.text.strip()} ({link_el.get('href')})")
            return len(items) > 0
    except Exception as e:
        print(f"  [ERROR] Connection failed: {e}")
        return False

async def main():
    mirrors = [
        "https://anitaku.to",
        "https://gogoanime.pe",
        "https://gogoanime.so",
        "https://gogoanime.run",
        "https://gogoanime3.co",
    ]
    
    connector = get_connector()
    async with aiohttp.ClientSession(connector=connector) as session:
        for mirror in mirrors:
            success = await test_mirror(mirror, session)
            if success:
                print(f"\n🎉 FOUND WORKABLE MIRROR: {mirror}")

if __name__ == "__main__":
    asyncio.run(main())
