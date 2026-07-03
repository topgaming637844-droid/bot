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

async def test_embed(url: str, name: str):
    print(f"\nTesting embed server '{name}' URL: {url}...")
    headers = {"User-Agent": get_random_user_agent(), "Referer": "https://anineko.to/"}
    connector = get_connector()
    async with aiohttp.ClientSession(connector=connector) as session:
        try:
            async with session.get(url, headers=headers, timeout=15) as response:
                text = await response.text()
                print(f"  Status: {response.status} | Length: {len(text)} characters")
                
                # Save to file
                scratch_dir = Path("c:/Users/monsm/OneDrive/Desktop/BOT/scratch")
                scratch_dir.mkdir(exist_ok=True)
                html_path = scratch_dir / f"embed_{name}.html"
                with open(html_path, "w", encoding="utf-8") as f:
                    f.write(text)
                print(f"  Saved HTML to {html_path}")
                
                soup = BeautifulSoup(text, "html.parser")
                print(f"  Title: '{soup.title.text.strip() if soup.title else 'No Title'}'")
                
                # Check for video tags or script contents with m3u8 or mp4
                videos = soup.find_all("video")
                print(f"  Videos: {len(videos)}")
                for v in videos:
                    print(f"    Video Src: {v.get('src')}")
                    for s in v.find_all("source"):
                        print(f"      Source: {s.get('src')} | Label: {s.get('label') or s.get('res')}")
                        
                # Search for player script configurations or sources
                scripts = soup.find_all("script")
                for i, scr in enumerate(scripts):
                    content = scr.string or ""
                    if content and ("m3u8" in content or "mp4" in content or "file" in content or "source" in content):
                        print(f"  Script {i+1} matches video files/streams. Content snippet (first 300 chars):")
                        print(content[:300].strip())
                        
        except Exception as e:
            print(f"  Failed: {e}")

async def main():
    await test_embed("https://vivibebe.site/b1b1bcf0e7bbfcbe", "vivibebe")
    await test_embed("https://bibiemb.xyz/ag06f391453e8e0e53ba2c00e2e46387a44h", "bibiemb")

if __name__ == "__main__":
    asyncio.run(main())
