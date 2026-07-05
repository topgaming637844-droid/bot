import sys
import codecs
sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())
sys.stderr = codecs.getwriter("utf-8")(sys.stderr.detach())

import asyncio
import os

# Adjust path to include root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.scraper import get_episodes_scraper, get_download_links_scraper, resolve_anime_slug_scraper
from app.utils.logging_config import logger
from config import config

config.PROXY_URL = None

async def test():
    print("Testing resolve_anime_slug_scraper for 'Kimetsu no Yaiba'...")
    slug = await resolve_anime_slug_scraper(
        title_romaji="Demon Slayer: Kimetsu no Yaiba",
        title_english="Demon Slayer: Kimetsu no Yaiba",
        synonyms=["Kimetsu no Yaiba"]
    )
    print(f"Resolved slug: {slug}")
    
    if not slug:
        slug = "kimetsu-no-yaiba"
        
    print(f"\nFetching episodes list for '{slug}'...")
    episodes_data = await get_episodes_scraper(slug)
    print(f"Total episodes fetched: {len(episodes_data.get('episodes', []))}")
    print(f"Poster URL: {episodes_data.get('poster_url')}")
    print(f"Description: {episodes_data.get('description')[:100] if episodes_data.get('description') else 'None'}...")
    
    if episodes_data.get('episodes'):
        first_ep = episodes_data['episodes'][0]
        print(f"\nFirst episode: ep {first_ep['ep_number']} - {first_ep['play_url']}")
        print("Fetching download links...")
        links = await get_download_links_scraper(first_ep['play_url'])
        print(f"Qualities resolved: {list(links.keys())}")
        for q, u in links.items():
            print(f"  {q}: {u[:80]}...")
    else:
        print("\nNo episodes found!")

if __name__ == "__main__":
    asyncio.run(test())
