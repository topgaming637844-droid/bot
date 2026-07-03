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
    domain = "https://gogoanime.by"
    print(f"Testing domain: {domain}...")
    url = f"{domain}/search.html?keyword=Naruto"
    headers = {"User-Agent": get_random_user_agent()}
    connector = get_connector()
    async with aiohttp.ClientSession(connector=connector) as session:
        try:
            async with session.get(url, headers=headers, timeout=15) as response:
                text = await response.text()
                
                # Save to file
                scratch_dir = Path("c:/Users/monsm/OneDrive/Desktop/BOT/scratch")
                scratch_dir.mkdir(exist_ok=True)
                html_path = scratch_dir / "by_response.html"
                with open(html_path, "w", encoding="utf-8") as f:
                    f.write(text)
                print(f"Saved HTML to {html_path}")
                
                soup = BeautifulSoup(text, "html.parser")
                print(f"Title: '{soup.title.text.strip() if soup.title else 'No Title'}'")
                
                # Let's see some class names of elements
                print("\nInspecting some divs and lists:")
                lists = soup.find_all("ul")
                print(f"Total ul elements: {len(lists)}")
                for i, lst in enumerate(lists):
                    classes = lst.get("class", [])
                    print(f"  ul {i+1} classes: {classes} | child li count: {len(lst.find_all('li'))}")
                    
                # Search for links containing "/category/" or similar
                links = soup.find_all("a")
                category_links = [l.get("href") for l in links if l.get("href") and "/category/" in l.get("href")]
                print(f"\nLinks containing '/category/': {len(category_links)}")
                for link in category_links[:5]:
                    print(f"  - {link}")
                    
        except Exception as e:
            print(f"Failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())
