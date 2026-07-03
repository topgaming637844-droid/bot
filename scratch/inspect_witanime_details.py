from bs4 import BeautifulSoup
from pathlib import Path
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
            
            details = soup.select(".cat-post-details")
            print(f"Found {len(details)} details elements")
            
            out_lines = []
            for idx, d in enumerate(details):
                out_lines.append(f"\nDetails {idx+1}:\n")
                out_lines.append(d.prettify())
                out_lines.append("\n" + "="*50 + "\n")
                
            out_file = Path("c:/Users/monsm/OneDrive/Desktop/BOT/scratch/witanime_details.txt")
            with open(out_file, "w", encoding="utf-8") as f:
                f.writelines(out_lines)
            print(f"Saved to {out_file}")
                
if __name__ == "__main__":
    asyncio.run(main())
