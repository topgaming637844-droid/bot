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
    print("--- INSPECTING GOGOANIME.PE HTML ---")
    url = "https://gogoanime.pe/search.html?keyword=Naruto"
    connector = get_connector()
    headers = {"User-Agent": get_random_user_agent()}
    async with aiohttp.ClientSession(connector=connector) as session:
        try:
            async with session.get(url, headers=headers, timeout=15) as response:
                text = await response.text()
                print(f"Status: {response.status} | Length: {len(text)} characters")
                
                # Save to file
                scratch_dir = Path("c:/Users/monsm/OneDrive/Desktop/BOT/scratch")
                scratch_dir.mkdir(exist_ok=True)
                html_path = scratch_dir / "pe_response.html"
                with open(html_path, "w", encoding="utf-8") as f:
                    f.write(text)
                print(f"Saved HTML to {html_path}")
                
                soup = BeautifulSoup(text, "html.parser")
                print(f"Title: '{soup.title.text.strip() if soup.title else 'No Title'}'")
                
                # Find all list items, divs, or links containing "Naruto"
                links = soup.find_all("a")
                matches = []
                for link in links:
                    text_content = link.text.strip()
                    if "naruto" in text_content.lower():
                        matches.append((text_content, link.get("href")))
                print(f"Matches found: {len(matches)}")
                for m in matches[:5]:
                    print(f"  Match: {m}")
                    
        except Exception as e:
            print(f"Failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())
