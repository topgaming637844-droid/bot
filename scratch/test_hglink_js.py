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

async def main():
    url = "https://hglink.to/main.js?v=1.1.8"
    headers = {
        "User-Agent": get_random_user_agent(),
        "Referer": "https://hglink.to/e/byra8rl00t20"
    }
    connector = get_connector()
    async with aiohttp.ClientSession(connector=connector) as session:
        try:
            async with session.get(url, headers=headers) as response:
                print(f"Status: {response.status}")
                text = await response.text()
                
                # Save script
                out_path = Path("c:/Users/monsm/OneDrive/Desktop/BOT/scratch/hglink_main.js")
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write(text)
                print(f"Saved main.js to {out_path}")
                
        except Exception as e:
            print(f"Failed to fetch script: {e}")

if __name__ == "__main__":
    asyncio.run(main())
