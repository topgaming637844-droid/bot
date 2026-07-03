import asyncio
import aiohttp
import sys
import re
import json
import base64
from pathlib import Path
from bs4 import BeautifulSoup
from urllib.parse import urljoin, quote

# Add project root to path
project_root = Path("c:/Users/monsm/OneDrive/Desktop/BOT")
sys.path.append(str(project_root))

from config import config
from app.utils.user_agents import get_random_user_agent
from app.services.anilist import get_connector

def decrypt_resource(resource_data, config_settings):
    reversed_data = resource_data[::-1]
    reversed_data = re.sub(r'[^A-Za-z0-9+/=]', '', reversed_data)
    
    index_key_bytes = base64.b64decode(config_settings["k"])
    index_key = index_key_bytes.decode("utf-8")
    param_offset = config_settings["d"][int(index_key)]
    
    decoded_bytes = base64.b64decode(reversed_data)
    if param_offset > 0:
        decoded_bytes = decoded_bytes[:-param_offset]
    decoded_resource = decoded_bytes.decode("utf-8")
    
    framework_hash = "23a97133-caf3-4eb4-9466-93d0a4ff8198"
    if re.match(r"^https://yonaplay\.net/embed\.php\?id=\d+$", decoded_resource):
        return decoded_resource + "&apiKey=" + framework_hash
    return decoded_resource

def decrypt_episodes(processed_episode_data):
    parts = processed_episode_data.split('.')
    data_bytes = base64.b64decode(parts[0])
    key_bytes = base64.b64decode(parts[1])
    
    decrypted_chars = []
    for i in range(len(data_bytes)):
        decrypted_chars.append(chr(data_bytes[i] ^ key_bytes[i % len(key_bytes)]))
        
    decrypted_str = "".join(decrypted_chars)
    return json.loads(decrypted_str)

async def resolve_anime_info(ep_url, session):
    headers = {"User-Agent": get_random_user_agent()}
    try:
        async with session.get(ep_url, headers=headers, timeout=10) as resp:
            if resp.status == 200:
                html = await resp.read()
                text = html.decode("utf-8", errors="ignore")
                
                match = re.search(r'href="https://[^/]+/anime/([^/"]+)/"', text)
                if match:
                    slug = match.group(1)
                    soup = BeautifulSoup(text, "html.parser")
                    anime_link = soup.find("a", href=lambda h: h and f"/anime/{slug}/" in h)
                    title = anime_link.text.strip() if anime_link else slug.replace("-", " ").title()
                    return {"title": title, "slug": slug}
    except Exception as e:
        print(f"Error resolving ep {ep_url}: {e}")
    return None

async def test_full_flow():
    query = "Naruto"
    search_url = f"https://witanime.pics/?search_param=anime&s={quote(query)}"
    print(f"1. Searching WitAnime for: {query}")
    
    headers = {"User-Agent": get_random_user_agent()}
    connector = get_connector()
    async with aiohttp.ClientSession(connector=connector) as session:
        async with session.get(search_url, headers=headers) as resp:
            html = await resp.text()
            
        soup = BeautifulSoup(html, "html.parser")
        details = soup.select(".cat-post-details h2 a")
        print(f"Found {len(details)} search results.")
        
        # Resolve parent series
        resolve_tasks = []
        for a in details[:5]:
            href = a.get("href")
            if "/anime/" in href:
                slug = href.split("/anime/")[1].strip("/")
                print(f"  Direct anime link: Title='{a.text.strip()}' | Slug='{slug}'")
            elif "/episode/" in href:
                resolve_tasks.append(resolve_anime_info(href, session))
                
        resolved = await asyncio.gather(*resolve_tasks)
        resolved_animes = [r for r in resolved if r]
        print(f"Resolved parent series from episodes: {resolved_animes}")
        
        if not resolved_animes:
            print("No anime series resolved.")
            return
            
        target_slug = resolved_animes[0]["slug"]
        anime_url = f"https://witanime.pics/anime/{target_slug}/"
        print(f"\n2. Loading TV Series details page: {anime_url}")
        async with session.get(anime_url, headers=headers) as resp:
            html = await resp.text()
            
        # Get episode list
        match = re.search(r"var processedEpisodeData = '([^']+)';", html)
        if not match:
            print("Could not find processedEpisodeData on TV series page.")
            return
            
        episodes = decrypt_episodes(match.group(1))
        print(f"Successfully decrypted {len(episodes)} episodes.")
        first_ep = episodes[0]
        print(f"First episode: Number='{first_ep.get('number')}' | URL='{first_ep.get('url')}'")
        
        # Get download links from the episode watch page
        play_url = first_ep.get("url")
        print(f"\n3. Loading watch page: {play_url}")
        async with session.get(play_url, headers=headers) as resp:
            play_html = await resp.text()
            
        # Extract servers
        play_soup = BeautifulSoup(play_html, "html.parser")
        servers = play_soup.select("#episode-servers li a, .episode-servers a, #watch-servers a")
        print(f"Found {len(servers)} servers in DOM:")
        server_names = []
        for s in servers:
            server_names.append(s.text.strip())
            
        zx_match = re.search(r'var _zX="([^"]+)"', play_html)
        zk_match = re.search(r'var _zK="([^"]+)"', play_html)
        
        if not zx_match or not zk_match:
            print("Failed to find _zX or _zK registries on watch page.")
            return
            
        resources = json.loads(base64.b64decode(zx_match.group(1)).decode("utf-8"))
        configs = json.loads(base64.b64decode(zk_match.group(1)).decode("utf-8"))
        
        decrypted_servers = {}
        for idx, (res, conf) in enumerate(zip(resources, configs)):
            decrypted_url = decrypt_resource(res, conf)
            s_name = server_names[idx] if idx < len(server_names) else f"Server-{idx+1}"
            decrypted_servers[s_name] = decrypted_url
            print(f"  Server '{s_name}': {decrypted_url}")

if __name__ == "__main__":
    asyncio.run(test_full_flow())
