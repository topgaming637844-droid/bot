import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import asyncio
import aiohttp
import re
import json
from app.services.scraper import get_browser_headers, safe_b64decode

async def main():
    url = "https://witanime.life/anime/naruto-shippuuden/"
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
                    print(f"Shippuden episodes count: {len(data)}")
                    if data:
                        print(f"First ep: {data[0]}")
                        print(f"Last ep: {data[-1]}")
                else:
                    print("encodedEpisodeData not found on Naruto Shippuuden page")

asyncio.run(main())
