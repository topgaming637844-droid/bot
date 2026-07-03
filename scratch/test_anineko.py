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

async def main():
    domain = "https://anineko.to"
    print(f"Testing domain: {domain}...")
    url = f"{domain}/search.html?keyword=Naruto"
    headers = {"User-Agent": get_random_user_agent()}
    connector = get_connector()
    async with aiohttp.ClientSession(connector=connector) as session:
        try:
            async with session.get(url, headers=headers, timeout=15) as response:
                text = await response.text()
                print(f"Status: {response.status} | Length: {len(text)} characters")
                
                soup = BeautifulSoup(text, "html.parser")
                page_title = soup.title.text.strip() if soup.title else "No Title"
                print(f"Title: '{page_title}'")
                
                items = soup.select("ul.items li")
                print(f"Found {len(items)} items using selector 'ul.items li'")
                for i, item in enumerate(items[:3]):
                    link_el = item.select_one("p.name a")
                    if link_el:
                        print(f"  Result {i+1}: {link_el.text.strip()} ({link_el.get('href')})")
                        
        except Exception as e:
            print(f"Failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())
