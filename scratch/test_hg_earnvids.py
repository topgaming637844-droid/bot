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
                
                # Save HTML to file
                scratch_dir = Path("c:/Users/monsm/OneDrive/Desktop/BOT/scratch")
                scratch_dir.mkdir(exist_ok=True)
                html_path = scratch_dir / f"embed_{name}.html"
                with open(html_path, "w", encoding="utf-8") as f:
                    f.write(text)
                print(f"  Saved HTML to {html_path}")
                
                soup = BeautifulSoup(text, "html.parser")
                
                # Look for scripts containing mp4, m3u8, or player setup
                scripts = soup.find_all("script")
                for i, scr in enumerate(scripts):
                    content = scr.string or ""
                    if content and ("mp4" in content or "m3u8" in content or "file" in content or "sources" in content):
                        print(f"  Script {i+1} matches video: Content snippet (first 300 chars):")
                        print(content[:300].strip())
                        
        except Exception as e:
            print(f"  Failed: {e}")

async def main():
    await test_embed("https://otakuhg.site/e/mj5b6zej2qc8", "streamhg")
    await test_embed("https://otakuvid.online/embed/upzfvdqh0kxy", "earnvids")

if __name__ == "__main__":
    asyncio.run(main())
