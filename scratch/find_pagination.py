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
            html = await resp.text()
            soup = BeautifulSoup(html, "html.parser")
            
            # Find all links with page
            links = soup.find_all("a")
            print("Links containing '/page/' or page numbers:")
            count = 0
            for a in links:
                href = a.get("href", "")
                if "/page/" in href or (a.text.strip().isdigit() and len(a.text.strip()) < 3):
                    print(f"Text: {a.text.strip()}, Href: {href}")
                    count += 1
            if count == 0:
                print("No page links found.")
                
            # Print elements with class pagination or similar
            for c in ["pagination", "page-numbers", "pagenavi", "navigation"]:
                els = soup.select(f"[class*='{c}']")
                print(f"\nElements matching class containing '{c}':")
                for el in els:
                    print(f"Tag: {el.name}, Class: {el.get('class')}")
                    # Print sub-links
                    for sub_a in el.find_all("a"):
                        print(f"  Sub Link: {sub_a.text.strip()} -> {sub_a.get('href')}")

asyncio.run(main())
