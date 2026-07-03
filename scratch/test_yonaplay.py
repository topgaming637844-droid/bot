import asyncio
import aiohttp
import sys
import re
from pathlib import Path

# Add project root to path
project_root = Path("c:/Users/monsm/OneDrive/Desktop/BOT")
sys.path.append(str(project_root))

from config import config
from app.utils.user_agents import get_random_user_agent
from app.services.anilist import get_connector

async def main():
    url = "https://yonaplay.net/embed.php?id=20350&apiKey=23a97133-caf3-4eb4-9466-93d0a4ff8198"
    headers = {
        "User-Agent": get_random_user_agent(),
        "Referer": "https://witanime.pics/"
    }
    connector = get_connector()
    async with aiohttp.ClientSession(connector=connector) as session:
        try:
            async with session.get(url, headers=headers) as response:
                print(f"Status: {response.status}")
                text = await response.text()
                
                # Save page to inspect
                out_path = Path("c:/Users/monsm/OneDrive/Desktop/BOT/scratch/yonaplay.html")
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write(text)
                print(f"Saved yonaplay page to {out_path}")
                
                # Check for sources, m3u8, or mp4
                m3u8_matches = re.findall(r'["\']([^"\']+\.m3u8[^"\']*)["\']', text)
                print(f"Found {len(m3u8_matches)} .m3u8 links:")
                for m in m3u8_matches:
                    print("  ", m)
                    
                mp4_matches = re.findall(r'["\']([^"\']+\.mp4[^"\']*)["\']', text)
                print(f"Found {len(mp4_matches)} .mp4 links:")
                for m in mp4_matches:
                    print("  ", m)
                    
        except Exception as e:
            print(f"Failed to fetch yonaplay: {e}")

if __name__ == "__main__":
    asyncio.run(main())
