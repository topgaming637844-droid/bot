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
    url = f"{domain}/browser?keyword=Naruto"
    headers = {"User-Agent": get_random_user_agent()}
    connector = get_connector()
    async with aiohttp.ClientSession(connector=connector) as session:
        try:
            async with session.get(url, headers=headers, timeout=15) as response:
                text = await response.text()
                
                # Save to file
                scratch_dir = Path("c:/Users/monsm/OneDrive/Desktop/BOT/scratch")
                scratch_dir.mkdir(exist_ok=True)
                html_path = scratch_dir / "anineko_search.html"
                with open(html_path, "w", encoding="utf-8") as f:
                    f.write(text)
                print(f"Saved HTML to {html_path}")
                
                soup = BeautifulSoup(text, "html.parser")
                
                # Print all <a> tag hrefs and texts to see what they are
                links = soup.find_all("a")
                print(f"\nAll links on page ({len(links)}):")
                for i, link in enumerate(links):
                    print(f"  Link {i+1}: Text='{link.text.strip()}' | Href='{link.get('href')}'")
                    
        except Exception as e:
            print(f"Failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())
