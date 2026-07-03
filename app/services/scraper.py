import re
import json
import base64
import aiohttp
import asyncio
from bs4 import BeautifulSoup
from typing import List, Dict, Any, Optional
from urllib.parse import quote, urljoin
from config import config
from app.utils.user_agents import get_random_user_agent
from app.services.anilist import get_connector
from app.utils.logging_config import logger

class ScraperError(Exception):
    """Base exception for scraping operations."""
    pass

def decrypt_resource(resource_data: str, config_settings: Dict[str, Any]) -> str:
    """Decrypts secure embed server URLs from witanime configs."""
    try:
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
    except Exception:
        logger.exception("Error in process: failed to decrypt witanime resource")
        return ""

def decrypt_episodes(processed_episode_data: str) -> List[Dict[str, Any]]:
    """Decrypts TV series episode list stored in processedEpisodeData."""
    try:
        parts = processed_episode_data.split('.')
        data_bytes = base64.b64decode(parts[0])
        key_bytes = base64.b64decode(parts[1])
        
        decrypted_chars = []
        for i in range(len(data_bytes)):
            decrypted_chars.append(chr(data_bytes[i] ^ key_bytes[i % len(key_bytes)]))
            
        decrypted_str = "".join(decrypted_chars)
        return json.loads(decrypted_str)
    except Exception:
        logger.exception("Error in process: failed to decrypt episodes list")
        return []

def unpack_dean_edwards(packed_text: str) -> str:
    """Unpacks Dean Edwards packed Javascript block in Python."""
    try:
        # Match variables in: }('p_content', a, c, 'k_content'.split('|'))
        pattern = r"\}\s*\(\s*(['\"].*?['\"])\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(['\"].*?['\"])\s*\.split\(['\"]\|['\"]\)\)"
        match = re.search(pattern, packed_text, re.DOTALL)
        if not match:
            return ""
            
        p_raw, a_str, c_str, k_raw = match.groups()
        a = int(a_str)
        c = int(c_str)
        
        # Strip quotes and handle escaped quotes
        p = p_raw[1:-1]
        p = re.sub(r'\\(["\'])', r'\1', p)
        
        k_content = k_raw[1:-1]
        k = k_content.split("|")
        
        def replace_word(word_match):
            word = word_match.group(0)
            try:
                val = 0
                for char in word:
                    if char.isdigit():
                        digit = int(char)
                    else:
                        digit = ord(char.lower()) - ord('a') + 10
                    if digit >= a:
                        return word
                    val = val * a + digit
                if val < len(k) and k[val]:
                    return k[val]
            except Exception:
                pass
            return word

        unpacked = re.sub(r"\b\w+\b", replace_word, p)
        return unpacked.replace("\\'", "'")
    except Exception:
        logger.exception("Error in process: failed to unpack Dean Edwards packed JS")
        return ""

async def get_html(url: str, session: aiohttp.ClientSession) -> str:
    """Fetches HTML content with custom headers and optional proxy."""
    headers = {"User-Agent": get_random_user_agent(), "Referer": "https://witanime.pics/"}
    proxy_str = f" via proxy {config.PROXY_URL}" if config.PROXY_URL else ""
    logger.info(f"Scraping page: {url}{proxy_str}")
    
    if config.PROXY_URL:
        logger.info(f"Proxy used for request: {config.PROXY_URL}")
        
    try:
        async with session.get(url, headers=headers, timeout=15) as response:
            if response.status == 200:
                return await response.text()
            raise ScraperError(f"HTTP error {response.status} fetching {url}")
    except Exception as e:
        logger.exception(f"Error in process while fetching HTML from {url}")
        if not isinstance(e, ScraperError):
            raise ScraperError(f"Connection failed: {e}") from e
        raise

async def resolve_anime_info(ep_url: str, session: aiohttp.ClientSession) -> Optional[Dict[str, str]]:
    """Resolves parent anime details page from an episode watch page URL."""
    headers = {"User-Agent": get_random_user_agent(), "Referer": "https://witanime.pics/"}
    try:
        async with session.get(ep_url, headers=headers, timeout=10) as resp:
            if resp.status == 200:
                text = await resp.text()
                match = re.search(r'href="https://[^/]+/anime/([^/"]+)/"', text)
                if match:
                    slug = match.group(1)
                    soup = BeautifulSoup(text, "html.parser")
                    anime_link = soup.find("a", href=lambda h: h and f"/anime/{slug}/" in h)
                    title = anime_link.text.strip() if anime_link else slug.replace("-", " ").title()
                    return {"title": title, "slug": slug}
    except Exception:
        logger.exception(f"Error in process: failed to resolve parent anime from {ep_url}")
    return None

async def parse_m3u8_qualities(master_url: str, session: aiohttp.ClientSession) -> Dict[str, str]:
    """Parses master .m3u8 playlist to extract quality variant URLs."""
    headers = {"User-Agent": get_random_user_agent(), "Referer": "https://witanime.pics/"}
    proxy_str = f" via proxy {config.PROXY_URL}" if config.PROXY_URL else ""
    logger.info(f"Scraping page: {master_url}{proxy_str}")
    
    if config.PROXY_URL:
        logger.info(f"Proxy used for request: {config.PROXY_URL}")
        
    qualities = {}
    try:
        async with session.get(master_url, headers=headers, timeout=10) as response:
            if response.status != 200:
                logger.error(f"Error in process: master playlist returned status {response.status}")
                return {}
            data = await response.read()
            if data.startswith(b"\x89PNG"):
                data = data[252:]
            text = data.decode("utf-8")
            
            if "#EXTINF:" in text:
                logger.info("Playlist is a direct single-quality variant HLS stream.")
                return {"720p": master_url}
                
            lines = text.splitlines()
            current_info = None
            for line in lines:
                line = line.strip()
                if line.startswith("#EXT-X-STREAM-INF:"):
                    match_res = re.search(r'RESOLUTION=(\d+x\d+)', line)
                    match_name = re.search(r'NAME="([^"]+)"', line)
                    if match_name:
                        current_info = match_name.group(1).lower()
                    elif match_res:
                        height = match_res.group(1).split("x")[1]
                        current_info = f"{height}p"
                elif line and not line.startswith("#"):
                    if current_info:
                        variant_url = urljoin(master_url, line)
                        qualities[current_info] = variant_url
                        current_info = None
                        
            logger.info(f"Parsed qualities from master playlist: {list(qualities.keys())}")
    except Exception:
        logger.exception(f"Error in process while parsing master playlist {master_url}")
    return qualities

async def search_anime_scraper(title: str) -> List[Dict[str, Any]]:
    """Searches for anime on WitAnime and resolves unique parent series."""
    logger.info(f"Starting search for anime: {title}")
    if config.MOCK_MODE:
        logger.info("[MOCK MODE] Simulating search result on WitAnime.")
        return [{"title": f"{title} (TV)", "slug": "mock-anime-slug"}]

    search_url = f"https://witanime.pics/?search_param=anime&s={quote(title)}"
    
    for attempt in range(2):
        connector = get_connector()
        if attempt > 0:
            logger.info("Retrying WitAnime search directly (bypassing proxy)...")
            
        async with aiohttp.ClientSession(connector=connector) as session:
            try:
                html = await get_html(search_url, session)
                soup = BeautifulSoup(html, "html.parser")
                
                details = soup.select(".cat-post-details h2 a")
                logger.info(f"Found {len(details)} posts matching search query.")
                
                # Resolve parent series concurrently
                resolve_tasks = []
                direct_results = []
                seen_slugs = set()
                
                for a in details:
                    href = a.get("href")
                    if "/anime/" in href:
                        slug = href.split("/anime/")[1].strip("/")
                        if slug not in seen_slugs:
                            seen_slugs.add(slug)
                            direct_results.append({"title": a.text.strip(), "slug": slug})
                    elif "/episode/" in href:
                        resolve_tasks.append(resolve_anime_info(href, session))
                        
                resolved = await asyncio.gather(*resolve_tasks)
                for item in resolved:
                    if item and item["slug"] not in seen_slugs:
                        seen_slugs.add(item["slug"])
                        direct_results.append(item)
                        
                logger.info(f"Resolved {len(direct_results)} unique anime series from search results.")
                return direct_results[:10]  # Limit to top 10 results
            except Exception as e:
                if connector and ("proxy" in str(e).lower() or "socks" in str(e).lower() or "authentication failure" in str(e).lower()):
                    logger.warning(f"Proxy failure during WitAnime search: {e}. Disabling proxy.")
                    config.PROXY_URL = None
                    if attempt == 0:
                        continue
                logger.exception("Error in process while searching anime scraper")
                break
                
    return []

async def get_episodes_scraper(anime_slug: str) -> List[Dict[str, Any]]:
    """Retrieves the list of episodes for a WitAnime series slug, crawling pagination if present."""
    logger.info(f"جاري جلب قائمة الحلقات للأنمي: {anime_slug}")
    if config.MOCK_MODE:
        logger.info("[MOCK MODE] Generating mock episodes list.")
        return [{"ep_number": str(i), "play_url": f"https://mock-play-page.com/{anime_slug}-episode-{i}"} for i in range(1, 13)]

    connector = get_connector()
    episodes = []
    seen_urls = set()
    
    async with aiohttp.ClientSession(connector=connector) as session:
        page_num = 1
        while True:
            if page_num == 1:
                url = f"https://witanime.pics/anime/{anime_slug}/"
            else:
                url = f"https://witanime.pics/anime/{anime_slug}/page/{page_num}/"
                
            try:
                headers = {"User-Agent": get_random_user_agent(), "Referer": "https://witanime.pics/"}
                async with session.get(url, headers=headers, timeout=15) as response:
                    if response.status != 200:
                        logger.info(f"توقف جلب الصفحات عند الصفحة {page_num} بسبب رمز الحالة: {response.status}")
                        break
                    html = await response.text()
            except Exception as e:
                logger.warning(f"فشل الاتصال بالصفحة {page_num}: {e}")
                break

            match = re.search(r"var processedEpisodeData = '([^']+)';", html)
            if not match:
                if page_num == 1:
                    logger.info(f"لم يتم العثور على processedEpisodeData للأنمي {anime_slug}. يتم التعامل معه كفيلم فردي.")
                    return [{
                        "ep_number": "1",
                        "play_url": f"https://witanime.pics/anime/{anime_slug}/"
                    }]
                else:
                    break
                    
            episodes_data = decrypt_episodes(match.group(1))
            if not episodes_data:
                break
                
            new_episodes_found = 0
            for ep in episodes_data:
                ep_num = str(ep.get("number"))
                play_url = ep.get("url")
                if play_url.startswith("https://witanime.you"):
                    play_url = play_url.replace("https://witanime.you", "https://witanime.pics")
                elif play_url.startswith("https://witanime.life"):
                    play_url = play_url.replace("https://witanime.life", "https://witanime.pics")
                
                if play_url not in seen_urls:
                    seen_urls.add(play_url)
                    episodes.append({
                        "ep_number": ep_num,
                        "play_url": play_url
                    })
                    new_episodes_found += 1
            
            if new_episodes_found == 0:
                logger.info(f"لم يتم العثور على حلقات جديدة في الصفحة {page_num}. إيقاف جلب الصفحات.")
                break
                
            logger.info(f"تم جلب {new_episodes_found} حلقة جديدة من الصفحة {page_num}")
            page_num += 1
            
    def get_ep_num(e):
        try:
            return float(e["ep_number"])
        except ValueError:
            return 999999.0
    episodes.sort(key=get_ep_num)
    
    logger.info(f"إجمالي الحلقات المستخرجة للأنمي {anime_slug}: {len(episodes)}")
    return episodes

async def get_m3u8_from_embed(embed_url: str, session: aiohttp.ClientSession) -> Optional[str]:
    """Resolves and extracts .m3u8 master playlist using custom player unpacker."""
    headers = {"User-Agent": get_random_user_agent(), "Referer": "https://witanime.pics/"}
    
    # Try multiple known mirror player domains if it's hglink.to
    target_urls = [embed_url]
    if "hglink.to" in embed_url:
        video_id = embed_url.split("/e/")[1].strip("/")
        target_urls = [
            f"https://hanerix.com/e/{video_id}",
            f"https://masukestin.com/e/{video_id}"
        ]
        
    for url in target_urls:
        logger.info(f"Attempting to resolve embed playlist from: {url}")
        try:
            async with session.get(url, headers=headers, timeout=10) as response:
                if response.status != 200:
                    continue
                text = await response.text()
                
                # Check if page is Dean Edwards packed
                script_match = re.search(r"eval\(function\(p,a,c,k,e,d\).*?\.split\(['\"]\|['\"]\)\)\)", text, re.DOTALL)
                if script_match:
                    unpacked = unpack_dean_edwards(script_match.group(0))
                    m3u8_matches = re.findall(r'https?://[^\s"\']+\.m3u8[^\s"\']*', unpacked)
                    if m3u8_matches:
                        m3u8_url = m3u8_matches[0]
                        logger.info(f"Resolved streamwish mirror HLS stream: {m3u8_url}")
                        return m3u8_url
                else:
                    # Regular regex search inside non-packed body
                    match = re.search(r'const\s+src\s*=\s*["\']([^"\']+\.m3u8[^"\']*)["\']', text)
                    if not match:
                        match = re.search(r'src\s*:\s*["\']([^"\']+\.m3u8[^"\']*)["\']', text)
                    if not match:
                        match = re.search(r'["\']([^"\']+\.m3u8[^"\']*)["\']', text)
                    if match:
                        m3u8_url = match.group(1)
                        logger.info(f"Resolved master .m3u8 playlist: {m3u8_url}")
                        return m3u8_url
        except Exception:
            logger.exception(f"Error in process while resolving mirror embed URL {url}")
    return None

async def get_download_links_scraper(play_url: str) -> Dict[str, str]:
    """Parses the watch page, decrypts player registries, and extracts HLS playlists."""
    logger.info(f"Scraping download links from watch page: {play_url}")
    if config.MOCK_MODE:
        logger.info("[MOCK MODE] Returning mock direct download video paths.")
        return {
            "1080p": "https://test-videos.co.uk/vids/bigbuckbunny/mp4/h264/1080/Big_Buck_Bunny_1080_10s_30MB.mp4?mock_size=2500000000",
            "720p": "https://test-videos.co.uk/vids/bigbuckbunny/mp4/h264/720/Big_Buck_Bunny_720_10s_10MB.mp4?mock_size=2200000000",
        }

    connector = get_connector()
    async with aiohttp.ClientSession(connector=connector) as session:
        try:
            # Normalize play URL domain
            if "witanime.you" in play_url:
                play_url = play_url.replace("https://witanime.you", "https://witanime.pics")
                
            html = await get_html(play_url, session)
            
            # Find server labels/names inside DOM
            soup = BeautifulSoup(html, "html.parser")
            servers = soup.select("#episode-servers li a, .episode-servers a, #watch-servers a")
            server_names = [s.text.strip().lower() for s in servers]
            
            # Extract player registry keys
            zx_match = re.search(r'var _zX="([^"]+)"', html)
            zk_match = re.search(r'var _zK="([^"]+)"', html)
            
            if not zx_match or not zk_match:
                raise ScraperError("Failed to locate player registries (_zX / _zK) on watch page")
                
            resources = json.loads(base64.b64decode(zx_match.group(1)).decode("utf-8"))
            configs = json.loads(base64.b64decode(zk_match.group(1)).decode("utf-8"))
            
            resolved_links = {}
            priority_indices = []
            other_indices = []
            
            for idx, (res, conf) in enumerate(zip(resources, configs)):
                s_name = server_names[idx] if idx < len(server_names) else ""
                if "streamwish" in s_name or "hglink" in s_name:
                    priority_indices.append(idx)
                else:
                    other_indices.append(idx)
                    
            for idx in priority_indices + other_indices:
                res = resources[idx]
                conf = configs[idx]
                embed_url = decrypt_resource(res, conf)
                if embed_url:
                    m3u8_master = await get_m3u8_from_embed(embed_url, session)
                    if m3u8_master:
                        qualities = await parse_m3u8_qualities(m3u8_master, session)
                        resolved_links.update(qualities)
                        if resolved_links:
                            break  # Found working qualities, skip rest
                            
            if not resolved_links:
                raise ScraperError("Failed to parse any working HLS streams from embed servers")
                
            logger.info(f"Resolved {len(resolved_links)} download link qualities: {list(resolved_links.keys())}")
            return resolved_links
        except Exception:
            logger.exception("Error in process while scraping download links")
            return {}
