import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import asyncio
import aiohttp
from bs4 import BeautifulSoup
from urllib.parse import quote
from app.services.scraper import get_browser_headers

async def main():
    url = f"https://witanime.life/?search_param=animes&s={quote('Naruto')}"
    headers = get_browser_headers(url)
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            print(f"Search Status: {resp.status}")
            if resp.status == 200:
                html = await resp.text()
                soup = BeautifulSoup(html, "html.parser")
                details = soup.select(".anime-card-title a")
                print(f"Found {len(details)} matches:")
                for a in details:
                    print(f"Title: {a.text.strip()} -> Href: {a.get('href')}")

asyncio.run(main())
