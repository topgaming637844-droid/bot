import asyncio
import aiohttp
import sys
from pathlib import Path
from bs4 import BeautifulSoup

# Add project root to path
project_root = Path("c:/Users/monsm/OneDrive/Desktop/BOT")
sys.path.append(str(project_root))

from config import config
from app.utils.user_agents import get_random_user_agent
from app.services.anilist import get_connector

async def test_search():
    url = "https://witanime.pics/?search_param=anime&s=Naruto"
    print(f"Searching WitAnime for Naruto: {url}")
    headers = {"User-Agent": get_random_user_agent()}
    connector = get_connector()
    async with aiohttp.ClientSession(connector=connector) as session:
        try:
            async with session.get(url, headers=headers, timeout=10) as response:
                html = await response.text()
                soup = BeautifulSoup(html, "html.parser")
                
                # Let's search for anime links in the results grid
                # Usually they are inside divs with certain classes
                print("HTML title:", soup.title.string if soup.title else "No title")
                
                # Print any links containing '/anime/' or inside anime container elements
                anime_cards = soup.select(".anime-list-content, .anime-card, .anime-grid, .anime-post")
                print(f"Found {len(anime_cards)} anime card elements")
                
                links = soup.find_all("a", href=lambda h: h and "/anime/" in h)
                print(f"Found {len(links)} links containing '/anime/'")
                
                for idx, link in enumerate(links[:15]):
                    parent = link.parent
                    img = link.find("img")
                    title = link.text.strip() or (img.get("alt") if img else "") or parent.text.strip()
                    print(f"  {idx+1}: Link='{link.get('href')}' | Title='{title}'")
                    
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_search())
