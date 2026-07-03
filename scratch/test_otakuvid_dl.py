import asyncio
import aiohttp
from bs4 import BeautifulSoup
import sys
import re
from pathlib import Path

# Add project root to path
project_root = Path("c:/Users/monsm/OneDrive/Desktop/BOT")
sys.path.append(str(project_root))

from config import config
from app.utils.user_agents import get_random_user_agent
from app.services.anilist import get_connector

async def main():
    url = "https://otakuvid.online/download/upzfvdqh0kxy_n"
    print(f"Requesting download link page: {url}...")
    headers = {
        "User-Agent": get_random_user_agent(),
        "Referer": "https://otakuvid.online/d/upzfvdqh0kxy"
    }
    connector = get_connector()
    async with aiohttp.ClientSession(connector=connector) as session:
        try:
            async with session.get(url, headers=headers, timeout=15) as response:
                text = await response.text()
                print(f"Status: {response.status} | Length: {len(text)} characters")
                
                # Save to file
                scratch_dir = Path("c:/Users/monsm/OneDrive/Desktop/BOT/scratch")
                scratch_dir.mkdir(exist_ok=True)
                html_path = scratch_dir / "otakuvid_dl.html"
                with open(html_path, "w", encoding="utf-8") as f:
                    f.write(text)
                print(f"Saved HTML to {html_path}")
                
                soup = BeautifulSoup(text, "html.parser")
                print(f"Title: '{soup.title.text.strip() if soup.title else 'No Title'}'")
                
                # Find all links on this page
                links = soup.find_all("a")
                print(f"Total links on this page: {len(links)}")
                for i, link in enumerate(links):
                    href = link.get("href", "")
                    text_content = link.text.strip().replace("\n", " ")
                    print(f"  Link {i+1}: Text='{text_content}' | Href='{href}'")
                    
                # Check for scripts containing redirect or download URLs
                scripts = soup.find_all("script")
                print(f"\nScripts containing links/redirects:")
                for i, script in enumerate(scripts):
                    src = script.get("src")
                    content = script.string or ""
                    if src:
                        print(f"  Script {i+1} Src: '{src}'")
                    if content and ("location" in content or "download" in content or "http" in content or "window" in content):
                        print(f"  Script {i+1} inline content snippet: {content[:200].strip()}...")
                        
        except Exception as e:
            print(f"Failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())
