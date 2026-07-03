import asyncio
import aiohttp
import sys
import json
from pathlib import Path

# Add project root to path
project_root = Path("c:/Users/monsm/OneDrive/Desktop/BOT")
sys.path.append(str(project_root))

from config import config
from app.utils.user_agents import get_random_user_agent
from app.services.anilist import get_connector

async def test_api(video_id: str):
    # Test common API endpoints for hglink.to
    endpoints = [
        f"https://hglink.to/api/source/{video_id}",
        "https://hglink.to/api/source",
        "https://hglink.to/ajax/embed/source",
        f"https://hglink.to/source/{video_id}"
    ]
    
    headers = {
        "User-Agent": get_random_user_agent(),
        "Referer": f"https://hglink.to/e/{video_id}",
        "X-Requested-With": "XMLHttpRequest",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    connector = get_connector()
    async with aiohttp.ClientSession(connector=connector) as session:
        for ep in endpoints:
            print(f"Testing EP: {ep}")
            try:
                # Try POST with empty body or key
                payload = {"r": "", "d": "hglink.to"}
                async with session.post(ep, data=payload, headers=headers, timeout=10) as resp:
                    print(f"  POST Status: {resp.status}")
                    if resp.status == 200:
                        text = await resp.text()
                        print(f"  POST Success! Length: {len(text)}")
                        print(f"  Response: {text[:400]}")
                        continue
            except Exception as e:
                print(f"  POST failed: {e}")
                
            try:
                # Try GET
                async with session.get(ep, headers=headers, timeout=10) as resp:
                    print(f"  GET Status: {resp.status}")
                    if resp.status == 200:
                        text = await resp.text()
                        print(f"  GET Success! Length: {len(text)}")
                        print(f"  Response: {text[:400]}")
            except Exception as e:
                print(f"  GET failed: {e}")

async def main():
    await test_api("byra8rl00t20")

if __name__ == "__main__":
    asyncio.run(main())
