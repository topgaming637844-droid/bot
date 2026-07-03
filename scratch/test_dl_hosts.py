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

async def test_dl_host(url: str):
    print(f"\nTesting download host URL: {url}...")
    headers = {"User-Agent": get_random_user_agent()}
    connector = get_connector()
    async with aiohttp.ClientSession(connector=connector) as session:
        try:
            async with session.get(url, headers=headers, timeout=15) as response:
                text = await response.text()
                print(f"  Status: {response.status} | Length: {len(text)} characters")
                
                soup = BeautifulSoup(text, "html.parser")
                print(f"  Title: '{soup.title.text.strip() if soup.title else 'No Title'}'")
                
                # Check for video tags
                videos = soup.find_all("video")
                print(f"  Videos found: {len(videos)}")
                for v in videos:
                    print(f"    Video Src: '{v.get('src')}'")
                    sources = v.find_all("source")
                    for src in sources:
                        print(f"      Source: '{src.get('src')}' | Quality: '{src.get('label') or src.get('res')}'")
                
                # Find all anchors with file extensions (.mp4, etc) or with specific text like "Download" or containing video qualities
                links = soup.find_all("a")
                print(f"  Total links: {len(links)}")
                for i, link in enumerate(links):
                    href = link.get("href", "")
                    text_content = link.text.strip().replace("\n", " ")
                    if href and (".mp4" in href or "download" in href.lower() or "quality" in text_content.lower() or "1080" in text_content or "720" in text_content or "480" in text_content or "360" in text_content):
                        print(f"    Link {i+1}: Text='{text_content}' | Href='{href}'")
                        
        except Exception as e:
            print(f"  Failed: {e}")

async def main():
    urls = [
        "https://playmogo.com/d/46t7ghxhjcxj",
        "https://otakuvid.online/d/upzfvdqh0kxy",
        "https://otakuhg.site/d/mj5b6zej2qc8"
    ]
    for url in urls:
        await test_dl_host(url)

if __name__ == "__main__":
    asyncio.run(main())
