import asyncio
import aiohttp
import sys
from pathlib import Path
from urllib.parse import urljoin

# Add project root to path
project_root = Path("c:/Users/monsm/OneDrive/Desktop/BOT")
sys.path.append(str(project_root))

from config import config
from app.utils.user_agents import get_random_user_agent
from app.services.anilist import get_connector

async def main():
    url = "https://vivibebe.site/public/stream/b1b1bcf0e7bbfcbe/master.m3u8"
    print(f"Requesting master playlist: {url}...")
    headers = {
        "User-Agent": get_random_user_agent(),
        "Referer": "https://vivibebe.site/"
    }
    connector = get_connector()
    async with aiohttp.ClientSession(connector=connector) as session:
        try:
            async with session.get(url, headers=headers, timeout=15) as response:
                print(f"Status: {response.status}")
                text = await response.text()
                print("Content:")
                print(text)
                
                # If there are sub-playlists, resolve one of them
                lines = text.splitlines()
                playlist_url = None
                for line in lines:
                    if line.strip() and not line.startswith("#"):
                        playlist_url = urljoin(url, line.strip())
                        break
                        
                if playlist_url:
                    print(f"\nRequesting variant playlist: {playlist_url}...")
                    async with session.get(playlist_url, headers=headers, timeout=15) as sub_resp:
                        sub_text = await sub_resp.text()
                        print("Variant playlist content (first 20 lines):")
                        print("\n".join(sub_text.splitlines()[:20]))
                        
        except Exception as e:
            print(f"Failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())
