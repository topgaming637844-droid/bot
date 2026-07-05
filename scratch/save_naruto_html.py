import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import asyncio
import aiohttp
from app.services.scraper import get_browser_headers

async def main():
    url = "https://witanime.life/anime/naruto/"
    headers = get_browser_headers(url)
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            if resp.status == 200:
                html = await resp.text()
                with open("scratch/naruto_page.html", "w", encoding="utf-8") as f:
                    f.write(html)
                print("HTML saved to scratch/naruto_page.html")

asyncio.run(main())
