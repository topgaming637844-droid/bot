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
    url = "https://hanerix.com/e/5rzzsm2fl9b9"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://witanime.you/"
    }
    connector = get_connector()
    async with aiohttp.ClientSession(connector=connector) as session:
        try:
            print(f"Requesting {url}...")
            async with session.get(url, headers=headers) as response:
                print(f"Status: {response.status}")
                text = await response.text()
                
                # Check for eval(function(p,a,c,k,e,d)
                packed_matches = re.findall(r"eval\(function\(p,a,c,k,e,d\).*?\)", text)
                print(f"Found {len(packed_matches)} packed script matches.")
                
                for idx, match in enumerate(packed_matches):
                    print(f"Match {idx+1} length: {len(match)}")
                    print(match[:200] + " ... " + match[-200:])
                
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
