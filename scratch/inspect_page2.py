import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import asyncio
import aiohttp
import re
import json
from app.services.scraper import get_browser_headers, safe_b64decode

async def main():
    url = "https://witanime.life/anime/naruto/page/2/"
    headers = get_browser_headers(url)
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            print(f"Status: {resp.status}")
            if resp.status == 200:
                html = await resp.text()
                encoded_match = re.search(r"var encodedEpisodeData = '([^']+)';", html)
                if encoded_match:
                    decoded = safe_b64decode(encoded_match.group(1)).decode("utf-8")
                    data = json.loads(decoded)
                    print(f"Page 2 episodes count: {len(data)}")
                    if data:
                        print(f"First ep on page 2: {data[0]}")
                        print(f"Last ep on page 2: {data[-1]}")
                else:
                    print("encodedEpisodeData not found on page 2")

asyncio.run(main())
