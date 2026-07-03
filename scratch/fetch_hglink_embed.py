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
    url = "https://hglink.to/e/byra8rl00t20"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://witanime.pics/"
    }
    connector = get_connector()
    async with aiohttp.ClientSession(connector=connector) as session:
        try:
            print(f"Requesting {url}...")
            async with session.get(url, headers=headers, allow_redirects=True) as response:
                print(f"Final URL: {response.url}")
                print(f"Status: {response.status}")
                text = await response.text()
                
                # Check if there is eval(function(p,a,c,k,e,d)
                packed_matches = re.findall(r"eval\(function\(p,a,c,k,e,d\).*?\)", text)
                print(f"Found {len(packed_matches)} packed script matches.")
                
                for idx, match in enumerate(packed_matches):
                    print(f"Match {idx+1} length: {len(match)}")
                    print(match[:200] + " ... " + match[-200:])
                    
                # Save page HTML to debug
                out_path = Path("c:/Users/monsm/OneDrive/Desktop/BOT/scratch/hglink_final_page.html")
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write(text)
                print(f"Saved html to {out_path}")
                
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
