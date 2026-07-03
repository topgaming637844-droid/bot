import asyncio
import aiohttp
import sys
from pathlib import Path
from bs4 import BeautifulSoup
from urllib.parse import quote

# Add project root to path
project_root = Path("c:/Users/monsm/OneDrive/Desktop/BOT")
sys.path.append(str(project_root))

from config import config
from app.utils.user_agents import get_random_user_agent
from app.services.anilist import get_connector

async def main():
    ep_slug = quote("فيلم-naruto-movie-2-dai-gekitotsu-maboroshi-no-chiteiiseki-dattebayo")
    url = f"https://witanime.pics/episode/{ep_slug}/"
    print(f"Requesting episode page: {url}")
    headers = {"User-Agent": get_random_user_agent()}
    connector = get_connector()
    async with aiohttp.ClientSession(connector=connector) as session:
        async with session.get(url, headers=headers) as response:
            print(f"Status: {response.status}")
            html = await response.text()
            
            # Save HTML immediately
            out_file = Path("c:/Users/monsm/OneDrive/Desktop/BOT/scratch/witanime_episode.html")
            with open(out_file, "w", encoding="utf-8") as f:
                f.write(html)
            print(f"Saved episode HTML to {out_file}")
            
            soup = BeautifulSoup(html, "html.parser")
            
            # Print title safely
            title_text = soup.title.string if soup.title else "None"
            print("Title (ascii fallback):", title_text.encode('ascii', 'ignore').decode())
            
            # Find watch server links
            # WitAnime has watch servers list. Let's look for elements
            servers = soup.select("#episode-servers li a, .episode-servers a, #watch-servers a")
            print(f"Found {len(servers)} servers via selectors")
            for idx, s in enumerate(servers):
                s_text = s.text.strip().encode('ascii', 'ignore').decode()
                print(f"  Server {idx+1}: {s_text} | data-url={s.get('data-url')} | data-ep-id={s.get('data-ep-id')} | href={s.get('href')}")
                
            # If no servers, check other lists or list items
            if not servers:
                for idx, a in enumerate(soup.find_all("a")):
                    href = a.get("href", "")
                    # Usually witanime servers are loaded via AJAX or have data-url / base64 urls
                    if a.get("data-url") or "watch" in href or "server" in href:
                        a_text = a.text.strip().encode('ascii', 'ignore').decode()
                        print(f"  Potential Link {idx+1}: {a_text} | data-url={a.get('data-url')} | href={href}")

if __name__ == "__main__":
    asyncio.run(main())
