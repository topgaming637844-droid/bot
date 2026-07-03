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

async def main():
    slug = "boruto-naruto-next-generations"
    url = f"https://witanime.pics/anime/{slug}/"
    print(f"Requesting TV series page: {url}")
    headers = {"User-Agent": get_random_user_agent()}
    connector = get_connector()
    async with aiohttp.ClientSession(connector=connector) as session:
        async with session.get(url, headers=headers) as response:
            html = await response.text()
            soup = BeautifulSoup(html, "html.parser")
            
            # Save HTML
            out_file = Path("c:/Users/monsm/OneDrive/Desktop/BOT/scratch/witanime_tv.html")
            with open(out_file, "w", encoding="utf-8") as f:
                f.write(html)
            print(f"Saved TV HTML to {out_file}")
            
            # Print elements in .episodes-list-content or similar containers
            episodes = soup.select(".episodes-list-content a, .episodes-card-container a, .ep_list a")
            print(f"Found {len(episodes)} episodes via selectors")
            
            lines = []
            for idx, a in enumerate(episodes):
                lines.append(f"{idx+1}: href='{a.get('href')}' | text='{a.text.strip()}'\n")
                
            # If empty, let's find all links containing '/episode/' or inside '.episodes-card-title'
            if not episodes:
                ep_links = soup.find_all("a", href=lambda h: h and "/episode/" in h)
                print(f"Found {len(ep_links)} links containing '/episode/' via fallback")
                for idx, a in enumerate(ep_links):
                    lines.append(f"Fallback {idx+1}: href='{a.get('href')}' | text='{a.text.strip()}'\n")
                    
            out_links_file = Path("c:/Users/monsm/OneDrive/Desktop/BOT/scratch/witanime_tv_links.txt")
            with open(out_links_file, "w", encoding="utf-8") as f:
                f.writelines(lines)
            print(f"Saved episode links to {out_links_file}")

if __name__ == "__main__":
    asyncio.run(main())
