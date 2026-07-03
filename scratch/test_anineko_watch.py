import asyncio
import aiohttp
from bs4 import BeautifulSoup
import sys
from pathlib import Path

# Add project root to path
project_root = Path("c:/Users/monsm/OneDrive/Desktop/BOT")
sys.path.append(str(project_root))

from config import config
from app.utils.user_agents import get_random_user_agent
from app.services.anilist import get_connector

async def main():
    domain = "https://anineko.to"
    url = f"{domain}/watch/naruto"
    print(f"Requesting watch page: {url}...")
    headers = {"User-Agent": get_random_user_agent()}
    connector = get_connector()
    async with aiohttp.ClientSession(connector=connector) as session:
        try:
            async with session.get(url, headers=headers, timeout=15) as response:
                text = await response.text()
                print(f"Status: {response.status} | Length: {len(text)} characters")
                
                # Save to file
                scratch_dir = Path("c:/Users/monsm/OneDrive/Desktop/BOT/scratch")
                scratch_dir.mkdir(exist_ok=True)
                html_path = scratch_dir / "anineko_watch.html"
                with open(html_path, "w", encoding="utf-8") as f:
                    f.write(text)
                print(f"Saved HTML to {html_path}")
                
                soup = BeautifulSoup(text, "html.parser")
                print(f"Title: '{soup.title.text.strip() if soup.title else 'No Title'}'")
                
                # Print all <a> tags or iframes
                iframes = soup.find_all("iframe")
                print(f"\nIframes found ({len(iframes)}):")
                for i, iframe in enumerate(iframes):
                    print(f"  Iframe {i+1}: Src='{iframe.get('src')}'")
                    
                links = soup.find_all("a")
                print(f"\nTotal links on watch page: {len(links)}")
                
                # Look for episode-like links or buttons
                ep_links = []
                for link in links:
                    href = link.get("href", "")
                    text_content = link.text.strip()
                    # Check if href contains "ep" or "episode" or similar
                    if href and ("ep" in href.lower() or "watch" in href.lower() or "player" in href.lower()):
                        ep_links.append((text_content, href))
                        
                print(f"\nSample episode/player links found ({len(ep_links)}):")
                for text, href in ep_links[:20]:
                    print(f"  - Text: '{text}' | Href: '{href}'")
                    
        except Exception as e:
            print(f"Failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())
