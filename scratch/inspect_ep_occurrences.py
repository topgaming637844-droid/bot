import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import asyncio
import aiohttp
import re

async def main():
    # Set stdout encoding
    sys.stdout.reconfigure(encoding='utf-8')
    url = "https://witanime.life/anime/naruto/"
    headers = get_browser_headers(url)
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            html = await resp.text()
            print(f"HTML length: {len(html)}")
            
            # Search for episodes text in HTML
            for ep_num in [1, 50, 100, 120, 128, 129, 130, 200, 220]:
                text_to_find = f"الحلقة {ep_num}"
                matches = list(re.finditer(text_to_find, html))
                print(f"Found ep_num {ep_num}: {len(matches)} times")
                
            # Search for any page or next page buttons in Arabic
            for term in ["الصفحة", "التالي", "السابق", "المزيد", "عرض المزيد", "الصفحات"]:
                matches = list(re.finditer(term, html))
                print(f"Found term '{term}': {len(matches)} times")
                if matches:
                    # Print context of first match
                    start = max(0, matches[0].start() - 100)
                    end = min(len(html), matches[0].end() + 100)
                    print(f"  Context: {html[start:end].strip()}")

from app.services.scraper import get_browser_headers
asyncio.run(main())
