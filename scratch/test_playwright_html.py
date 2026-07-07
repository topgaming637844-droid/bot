import asyncio
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.scraper import get_html_headless

async def main():
    url = "https://witanime.life/"
    print(f"Fetching {url} using Playwright...")
    html = await get_html_headless(url)
    print("HTML Length:", len(html))
    if html:
        # Save first
        with open("scratch/witanime_home.html", "w", encoding="utf-8") as f:
            f.write(html)
        print("Saved to scratch/witanime_home.html")
        
        # Safe printing using sys.stdout.buffer or just ascii-safe strings
        print("Does it contain 'anime-card-container'?", "anime-card-container" in html)
        print("Does it contain 'episodes-card-container'?", "episodes-card-container" in html)
        print("Does it contain 'epcontent'?", "epcontent" in html)
        print("Does it contain 'epcard'?", "epcard" in html)
        print("Does it contain 'Cloudflare'?", "Cloudflare" in html or "cloudflare" in html.lower())
    else:
        print("HTML is empty!")

if __name__ == "__main__":
    asyncio.run(main())
