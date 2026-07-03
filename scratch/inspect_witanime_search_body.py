from bs4 import BeautifulSoup
from pathlib import Path

# Load search HTML
html_path = Path("c:/Users/monsm/OneDrive/Desktop/BOT/scratch/witanime_structure.txt")
# Wait, witanime_structure.txt is a log of links. Let's download the actual HTML search page and save it
import asyncio
import aiohttp
import sys
project_root = Path("c:/Users/monsm/OneDrive/Desktop/BOT")
sys.path.append(str(project_root))

from config import config
from app.utils.user_agents import get_random_user_agent
from app.services.anilist import get_connector

async def main():
    url = "https://witanime.pics/?search_param=anime&s=Naruto"
    headers = {"User-Agent": get_random_user_agent()}
    connector = get_connector()
    async with aiohttp.ClientSession(connector=connector) as session:
        async with session.get(url, headers=headers) as response:
            html = await response.text()
            soup = BeautifulSoup(html, "html.parser")
            
            # Find the main container of the posts
            posts = soup.select(".anime-list-content, .category-posts, .content")
            print(f"Found {len(posts)} content container elements")
            
            # Let's inspect the cards
            # In WitAnime, each anime card is usually inside a div with class 'anime-card-container' or similar
            cards = soup.select(".anime-card-container, .cat-post-thumbnail, .post-item")
            print(f"Found {len(cards)} post cards")
            
            out_lines = []
            for idx, card in enumerate(cards[:10]):
                out_lines.append(f"\nCard {idx+1}:\n")
                out_lines.append(card.prettify())
                out_lines.append("\n" + "="*50 + "\n")
                
            out_file = Path("c:/Users/monsm/OneDrive/Desktop/BOT/scratch/witanime_cards.txt")
            with open(out_file, "w", encoding="utf-8") as f:
                f.writelines(out_lines)
            print(f"Saved card structures to {out_file}")

if __name__ == "__main__":
    asyncio.run(main())
