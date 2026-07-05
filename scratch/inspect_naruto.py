import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import asyncio
import aiohttp
from bs4 import BeautifulSoup
from app.services.scraper import get_browser_headers

async def main():
    url = "https://witanime.life/anime/naruto/"
    headers = get_browser_headers(url)
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            print(f"Status: {resp.status}")
            html = await resp.text()
            soup = BeautifulSoup(html, "html.parser")
            
            # Find pagination elements
            pagination = soup.select(".pagination a, ul.pagination li a, .wp-pagenavi a")
            print("Pagination links found:")
            for a in pagination:
                print(f"Text: {a.text.strip()}, Href: {a.get('href')}")
                
            # Find episodes
            episodes = soup.select("a[href*='/episode/']")
            print(f"Total episodes found on page 1: {len(episodes)}")
            if episodes:
                print(f"First episode: {episodes[0].text.strip()} -> {episodes[0].get('href')}")
                print(f"Last episode: {episodes[-1].text.strip()} -> {episodes[-1].get('href')}")

asyncio.run(main())
