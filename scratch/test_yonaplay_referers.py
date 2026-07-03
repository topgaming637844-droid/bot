import asyncio
import aiohttp
import sys
from pathlib import Path

# Add project root to path
project_root = Path("c:/Users/monsm/OneDrive/Desktop/BOT")
sys.path.append(str(project_root))

from config import config
from app.utils.user_agents import get_random_user_agent
from app.services.anilist import get_connector

async def test_referer(referer: str):
    url = "https://yonaplay.net/embed.php?id=20350&apiKey=23a97133-caf3-4eb4-9466-93d0a4ff8198"
    print(f"Testing Referer: '{referer}'")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": referer,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9"
    }
    connector = get_connector()
    async with aiohttp.ClientSession(connector=connector) as session:
        try:
            async with session.get(url, headers=headers, timeout=10) as response:
                print(f"  Status: {response.status}")
                if response.status == 200:
                    text = await response.text()
                    print(f"  Success! Length: {len(text)}")
                    if "m3u8" in text or "mp4" in text or "source" in text:
                        print("  Found video streams in body!")
                        # print first line with m3u8
                        for line in text.splitlines():
                            if "m3u8" in line or "mp4" in line:
                                print(f"    {line.strip()[:150]}")
                    return True
        except Exception as e:
            print(f"  Error: {e}")
    return False

async def main():
    referers = [
        "https://witanime.pics/",
        "https://witanime.pics",
        "https://witanime.you/",
        "https://witanime.you",
        "https://witanime.net/",
        "https://witanime.net",
        "https://www.witanime.pics/",
        "https://www.witanime.pics",
        "https://www.witanime.net/",
        "https://www.witanime.net"
    ]
    for ref in referers:
        success = await test_referer(ref)
        if success:
            print("🎉 Success found!")
            break

if __name__ == "__main__":
    asyncio.run(main())
