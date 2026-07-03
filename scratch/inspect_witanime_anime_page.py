import asyncio
import aiohttp
import sys
import re
from pathlib import Path
from bs4 import BeautifulSoup
from urllib.parse import quote

# Add project root to path
project_root = Path("c:/Users/monsm/OneDrive/Desktop/BOT")
sys.path.append(str(project_root))

from config import config
from app.utils.user_agents import get_random_user_agent
from app.services.anilist import get_connector

async def main():
    slug = "naruto-movie-2-dai-gekitotsu-maboroshi-no-chiteiiseki-dattebayo"
    url = f"https://witanime.pics/anime/{slug}/"
    print(f"Requesting anime page: {url}")
    headers = {"User-Agent": get_random_user_agent()}
    connector = get_connector()
    async with aiohttp.ClientSession(connector=connector) as session:
        async with session.get(url, headers=headers) as response:
            print(f"Status: {response.status}")
            html = await response.text()
            
            # Save HTML
            out_file = Path("c:/Users/monsm/OneDrive/Desktop/BOT/scratch/witanime_anime.html")
            with open(out_file, "w", encoding="utf-8") as f:
                f.write(html)
            print(f"Saved anime page HTML to {out_file}")
            
            soup = BeautifulSoup(html, "html.parser")
            
            # Look for episode list elements
            # Usually they are inside divs with classes like 'episodes-card-container' or containing '/episode/'
            episodes = soup.select(".episodes-card-container a, .episodes-list a, .episodes-grid a")
            print(f"Found {len(episodes)} episodes via selectors")
            
            # Let's search all links containing '/episode/'
            ep_links = soup.find_all("a", href=lambda h: h and "/episode/" in h)
            print(f"Found {len(ep_links)} links containing '/episode/'")
            
            lines = []
            for idx, a in enumerate(ep_links):
                href = a.get("href", "")
                text = a.text.strip()
                lines.append(f"{idx+1}: href='{href}' | text='{text}'\n")
                
            out_links_file = Path("c:/Users/monsm/OneDrive/Desktop/BOT/scratch/witanime_anime_links.txt")
            with open(out_links_file, "w", encoding="utf-8") as f:
                f.writelines(lines)
            print(f"Saved episode links to {out_links_file}")

if __name__ == "__main__":
    asyncio.run(main())
