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
    print(f"Inspecting homepage of: {domain}...")
    headers = {"User-Agent": get_random_user_agent()}
    connector = get_connector()
    async with aiohttp.ClientSession(connector=connector) as session:
        try:
            async with session.get(domain, headers=headers, timeout=15) as response:
                text = await response.text()
                print(f"Status: {response.status} | Length: {len(text)} characters")
                
                soup = BeautifulSoup(text, "html.parser")
                
                # Check for forms
                forms = soup.find_all("form")
                print(f"Found {len(forms)} form(s) on the homepage:")
                for i, form in enumerate(forms):
                    print(f"  Form {i+1}: Action='{form.get('action')}' | Method='{form.get('method')}'")
                    inputs = form.find_all("input")
                    print(f"    Inputs: {[ (inp.get('name'), inp.get('type'), inp.get('id')) for inp in inputs ]}")
                    
                # Print some category links or general links on the homepage
                links = soup.find_all("a")
                print(f"Total links: {len(links)}")
                anime_links = [l.get("href") for l in links if l.get("href") and "/category/" in l.get("href")]
                print(f"Category links found: {len(anime_links)}")
                for link in anime_links[:3]:
                    print(f"  - {link}")
                    
        except Exception as e:
            print(f"Failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())
