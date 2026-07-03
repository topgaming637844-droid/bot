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
        async with session.get(url, headers=headers) as response:
            text = await response.text()
            
    # Find eval
    script_match = re.search(r"eval\(function\(p,a,c,k,e,d\).*?\)", text, re.DOTALL)
    if script_match:
        packed = script_match.group(0)
        print(f"Packed length: {len(packed)}")
        # Print first 200 and last 200 characters of the packed script
        print("START:")
        print(packed[:300])
        print("END:")
        print(packed[-300:])
        
        # Save to file
        out_path = Path("c:/Users/monsm/OneDrive/Desktop/BOT/scratch/packed_js_sample.txt")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(packed)
        print(f"Saved packed JS sample to {out_path}")
    else:
        print("No eval match found!")

if __name__ == "__main__":
    asyncio.run(main())
