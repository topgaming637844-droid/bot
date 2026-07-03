import asyncio
import aiohttp
from bs4 import BeautifulSoup
import sys
import re
from pathlib import Path

# Add project root to path
project_root = Path("c:/Users/monsm/OneDrive/Desktop/BOT")
sys.path.append(str(project_root))

from config import config
from app.utils.user_agents import get_random_user_agent
from app.services.scraper import get_html, search_anime_scraper
from app.services.anilist import get_connector

async def main():
    print("--- DEBUGGING SCRAPER SEARCH AND SAVING HTML ---")
    
    test_term = "Naruto"
    connector = get_connector()
    async with aiohttp.ClientSession(connector=connector) as session:
        url = f"{config.GOGOANIME_BASE_URL}/search.html?keyword={test_term}"
        headers = {"User-Agent": get_random_user_agent()}
        try:
            async with session.get(url, headers=headers, timeout=15) as response:
                text = await response.text()
                
                redirect_match = re.search(r"window\.location\.replace\('([^']+)'\)", text)
                if redirect_match:
                    redirect_url = redirect_match.group(1)
                    
                    async with session.get(redirect_url, headers=headers, timeout=15) as next_resp:
                        html = await next_resp.text()
                        
                        # Save HTML to scratch directory for inspection
                        scratch_dir = Path("c:/Users/monsm/OneDrive/Desktop/BOT/scratch")
                        scratch_dir.mkdir(exist_ok=True)
                        html_path = scratch_dir / "response.html"
                        with open(html_path, "w", encoding="utf-8") as f:
                            f.write(html)
                        print(f"Saved {len(html)} characters to {html_path}")
                        
                        soup = BeautifulSoup(html, "html.parser")
                        # Print some elements
                        links = soup.find_all("a")
                        print(f"Total links found: {len(links)}")
                        # Print titles or text containing "Naruto"
                        matches = []
                        for link in links:
                            text_content = link.text.strip()
                            if "naruto" in text_content.lower():
                                matches.append((text_content, link.get("href")))
                        print(f"Links matching 'Naruto': {matches}")
                else:
                    print("No redirect found.")
        except Exception as e:
            print(f"Failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())
