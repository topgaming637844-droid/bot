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
    url = "https://witanime.pics/?search_param=anime&s=Naruto"
    headers = {"User-Agent": get_random_user_agent()}
    connector = get_connector()
    async with aiohttp.ClientSession(connector=connector) as session:
        async with session.get(url, headers=headers) as response:
            html = await response.text()
            soup = BeautifulSoup(html, "html.parser")
            
            output_lines = []
            output_lines.append(f"Page Title: {soup.title.string if soup.title else 'None'}\n")
            
            # Find elements that contain search results
            # WitAnime search results are typically inside div cards. Let's look at all links
            links = soup.find_all("a")
            output_lines.append(f"Total links found: {len(links)}\n")
            
            for idx, a in enumerate(links):
                href = a.get("href", "")
                text = a.text.strip()
                title_attr = a.get("title", "")
                # Find img inside anchor
                img = a.find("img")
                img_alt = img.get("alt", "") if img else ""
                
                output_lines.append(f"Link {idx+1}: href='{href}' | text='{text}' | title='{title_attr}' | img_alt='{img_alt}'\n")
                
            out_file = Path("c:/Users/monsm/OneDrive/Desktop/BOT/scratch/witanime_structure.txt")
            with open(out_file, "w", encoding="utf-8") as f:
                f.writelines(output_lines)
            print(f"Saved structure to {out_file}")

if __name__ == "__main__":
    asyncio.run(main())
