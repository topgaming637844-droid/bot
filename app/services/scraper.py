import re
import json
import base64
import aiohttp
import asyncio
from bs4 import BeautifulSoup
from typing import List, Dict, Any, Optional
from urllib.parse import quote, urljoin

WITANIME_DOMAIN = "witanime.life"
from config import config
from app.utils.user_agents import get_random_user_agent
from app.services.anilist import get_connector
from app.utils.logging_config import logger

class ScraperError(Exception):
    """Base exception for scraping operations."""
    pass

def safe_b64decode(data: str) -> bytes:
    """Safely decodes Base64 data, adding missing padding and stripping illegal characters."""
    if isinstance(data, str):
        data_str = data.strip()
    else:
        data_str = data.decode("utf-8", errors="ignore").strip()
    data_str = re.sub(r'[^A-Za-z0-9+/=]', '', data_str)
    missing_padding = len(data_str) % 4
    if missing_padding:
        data_str += '=' * (4 - missing_padding)
    return base64.b64decode(data_str)

def normalize_quality_name(name: str) -> str:
    name = name.lower().strip()
    if "1080" in name or "fhd" in name or "high" in name:
        return "1080p"
    if "720" in name or "hd" in name:
        return "720p"
    if "480" in name or "sd" in name:
        return "480p"
    if "360" in name or "mobile" in name:
        return "360p"
    if "240" in name or "low" in name:
        return "240p"
    if not name.endswith("p") and name.isdigit():
        return f"{name}p"
    return name

def decrypt_resource(resource_data: str, config_settings: Dict[str, Any]) -> str:
    """Decrypts secure embed server URLs from witanime configs."""
    try:
        reversed_data = resource_data[::-1]
        reversed_data = re.sub(r'[^A-Za-z0-9+/=]', '', reversed_data)
        
        index_key_bytes = safe_b64decode(config_settings["k"])
        index_key = index_key_bytes.decode("utf-8")
        param_offset = config_settings["d"][int(index_key)]
        
        decoded_bytes = safe_b64decode(reversed_data)
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
        data_bytes = safe_b64decode(parts[0])
        key_bytes = safe_b64decode(parts[1])
        
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
    except Exception:
        logger.exception("Error in process: failed to unpack Dean Edwards packed JS")
        return ""

try:
    from curl_cffi.requests import AsyncSession as CurlAsyncSession
    CURL_CFFI_AVAILABLE = True
except ImportError:
    CURL_CFFI_AVAILABLE = False
    CurlAsyncSession = None

GLOBAL_COOKIE_JAR: Optional[aiohttp.CookieJar] = None

def get_global_cookie_jar() -> aiohttp.CookieJar:
    global GLOBAL_COOKIE_JAR
    if GLOBAL_COOKIE_JAR is None:
        GLOBAL_COOKIE_JAR = aiohttp.CookieJar()
    return GLOBAL_COOKIE_JAR

WITANIME_DOMAINS = ["witanime.life", "witanime.pics", "witanime.com", "witanime.red", "witanime.site"]

def get_browser_headers(referer: str = f"https://{WITANIME_DOMAIN}/") -> dict:
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Language": "ar,en-US;q=0.9,en;q=0.8",
        "Referer": referer,
        "Sec-Ch-Ua": '"Chromium";v="123", "Not:A-Brand";v="8", "Google Chrome";v="123"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin" if "witanime" in referer else "cross-site",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1"
    }

async def harvest_session_cookies(domain: str, session: Any):
    """Harvests initial session cookies from base domain before sending queries."""
    base_url = f"https://{domain}/"
    try:
        headers = get_browser_headers(base_url)
        if hasattr(session, 'get') and hasattr(session, 'impersonate'):
            resp = await session.get(base_url, headers=headers, timeout=6)
            if resp.status_code == 200:
                logger.info(f"Successfully harvested session cookies from {domain} via TLS Impersonation")
            elif resp.status_code == 403:
                logger.warning(f"Session cookie harvest on {domain} encountered 403 Forbidden.")
        else:
            async with session.get(base_url, headers=headers, ssl=False, timeout=6) as resp:
                if resp.status == 200:
                    logger.info(f"Successfully harvested session cookies from {domain}")
                elif resp.status == 403:
                    logger.warning(f"Session cookie harvest on {domain} encountered 403 Forbidden.")
    except Exception as e:
        logger.warning(f"Failed harvesting cookies from {domain}: {e}")

async def get_html(url: str, session: Any) -> str:
    """Fetches HTML content with browser headers and cookie session."""
    headers = get_browser_headers(url)
    logger.info(f"Scraping page: {url}")
    
    try:
        if hasattr(session, 'get') and hasattr(session, 'impersonate'):
            response = await session.get(url, headers=headers, timeout=12)
            if response.status_code == 200:
                return response.text
            elif response.status_code == 403:
                logger.warning(f"HTTP 403 Forbidden encountered on {url}. Cloudflare protection active.")
                return "STATUS_403_FORBIDDEN"
            logger.warning(f"HTTP status {response.status_code} fetching {url}")
            return ""
        else:
            async with session.get(url, headers=headers, ssl=False, timeout=12) as response:
                if response.status == 200:
                    return await response.text()
                elif response.status == 403:
                    logger.warning(f"HTTP 403 Forbidden encountered on {url}. Cloudflare protection active.")
                    return "STATUS_403_FORBIDDEN"
                logger.warning(f"HTTP status {response.status} fetching {url}")
                return ""
    except Exception as e:
        logger.warning(f"Connection failed for {url}: {e}")
        return ""

async def resolve_anime_info(ep_url: str, session: aiohttp.ClientSession) -> Optional[Dict[str, str]]:
    """Resolves parent anime details page from an episode watch page URL."""
    headers = get_browser_headers(ep_url)
    try:
        async with session.get(ep_url, headers=headers, ssl=False, timeout=10) as resp:
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
    headers = get_browser_headers(master_url)
    qualities = {}
    try:
        async with session.get(master_url, headers=headers, ssl=False, timeout=10) as response:
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
                        current_info = normalize_quality_name(match_name.group(1))
                    elif match_res:
                        height = match_res.group(1).split("x")[1]
                        current_info = normalize_quality_name(f"{height}p")
                elif line and not line.startswith("#"):
                    if current_info:
                        variant_url = urljoin(master_url, line)
                        qualities[current_info] = variant_url
                        current_info = None
                        
            logger.info(f"Parsed qualities from master playlist: {list(qualities.keys())}")
    except Exception:
        logger.exception(f"Error in process while parsing master playlist {master_url}")
    return qualities

async def _run_scraper_search(session: Any, title: str, search_queries: List[str]) -> List[Dict[str, Any]]:
    for idx, domain in enumerate(WITANIME_DOMAINS):
        if idx > 0:
            await asyncio.sleep(1.5)  # Rate-limit mitigation delay
            
        await harvest_session_cookies(domain, session)
        is_403_blocked = False
        
        for q_path in search_queries:
            search_url = f"https://{domain}/{q_path.lstrip('/')}"
            try:
                html = await get_html(search_url, session)
                if html == "STATUS_403_FORBIDDEN":
                    logger.warning(f"Domain {domain} returned 403 Forbidden. Aborting further domain query loops.")
                    is_403_blocked = True
                    break
                if not html:
                    continue
                soup = BeautifulSoup(html, "html.parser")
                details = soup.select(".anime-card-title a")
                if not details:
                    details = soup.select(".anime-card-details a, .anime-card-poster a, h3 a")
                
                if details:
                    logger.info(f"Found {len(details)} posts matching search query on {domain}.")
                    resolve_tasks = []
                    direct_results = []
                    seen_slugs = set()
                    
                    for a in details:
                        href = a.get("href", "")
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
                            
                    if direct_results:
                        logger.info(f"Resolved {len(direct_results)} unique anime series from {domain}.")
                        return direct_results[:10]
            except Exception as e:
                logger.warning(f"Error searching {domain}: {e}")
                
        if is_403_blocked:
            break
                
    # Direct slug resolution fallback if search queries returned empty
    from app.utils.match import sanitize_search_query
    possible_slug = sanitize_search_query(title).replace(" ", "-")
    slug_candidates = [
        possible_slug,
        f"{possible_slug}-tv",
        f"{possible_slug}-season-1"
    ]
    for domain in WITANIME_DOMAINS:
        for slug_cand in slug_candidates:
            test_url = f"https://{domain}/anime/{slug_cand}/"
            try:
                if hasattr(session, 'get') and hasattr(session, 'impersonate'):
                    resp = await session.get(test_url, headers=get_browser_headers(test_url), timeout=5)
                    if resp.status_code == 200:
                        logger.info(f"Direct slug fallback matched: {test_url}")
                        return [{"title": title, "slug": slug_cand}]
                else:
                    async with session.get(test_url, headers=get_browser_headers(test_url), ssl=False, timeout=5) as resp:
                        if resp.status == 200:
                            logger.info(f"Direct slug fallback matched: {test_url}")
                            return [{"title": title, "slug": slug_cand}]
            except Exception:
                pass

    return []

async def search_anime_scraper(title: str) -> List[Dict[str, Any]]:
    """Searches for anime on WitAnime and resolves unique parent series with multi-domain fallback."""
    normalized_title = title.replace("×", " x ").replace(":", " ").replace("-", " ")
    normalized_title = " ".join(normalized_title.split())
    
    logger.info(f"Starting search for anime: {normalized_title} (original: {title})")
    if config.MOCK_MODE:
        logger.info("[MOCK MODE] Simulating search result on WitAnime.")
        return [{"title": f"{title} (TV)", "slug": "mock-anime-slug"}]

    search_queries = [
        f"?search_param=animes&s={quote(normalized_title)}",
        f"?s={quote(normalized_title)}"
    ]
    
    if CURL_CFFI_AVAILABLE and CurlAsyncSession:
        logger.info("Using curl_cffi TLS Impersonation (chrome120) for Cloudflare bypass.")
        async with CurlAsyncSession(impersonate="chrome120") as session:
            return await _run_scraper_search(session, title, search_queries)
    else:
        connector = get_connector()
        async with aiohttp.ClientSession(connector=connector, cookie_jar=get_global_cookie_jar()) as session:
            return await _run_scraper_search(session, title, search_queries)

async def get_episodes_scraper(anime_slug: str) -> Dict[str, Any]:
    """Retrieves the list of episodes for a WitAnime series slug, crawling pagination if present."""
    logger.info(f"جاري جلب قائمة الحلقات للأنمي: {anime_slug}")
    if config.MOCK_MODE:
        logger.info("[MOCK MODE] Generating mock episodes list.")
        return {
            "episodes": [{"ep_number": str(i), "play_url": f"https://mock-play-page.com/{anime_slug}-episode-{i}"} for i in range(1, 13)],
            "poster_url": "https://test-videos.co.uk/vids/bigbuckbunny/mp4/h264/720/Big_Buck_Bunny_720_10s_10MB.mp4",
            "description": "قصة أنمي تجريبية لوضع المحاكاة.",
            "duration": "24 دقيقة"
        }

    connector = get_connector()
    episodes = []
    seen_urls = set()
    
    poster_url = None
    description = None
    duration = None
    
    async with aiohttp.ClientSession(connector=connector) as session:
        active_domain = WITANIME_DOMAIN
        # Determine working domain first
        for domain in WITANIME_DOMAINS:
            test_u = f"https://{domain}/anime/{anime_slug}/"
            try:
                async with session.get(test_u, headers=get_browser_headers(test_u), ssl=False, timeout=8) as r:
                    if r.status == 200:
                        active_domain = domain
                        break
            except Exception:
                pass
                
        page_num = 1
        while True:
            if page_num == 1:
                url = f"https://{active_domain}/anime/{anime_slug}/"
            else:
                url = f"https://{active_domain}/anime/{anime_slug}/page/{page_num}/"
                
            try:
                headers = get_browser_headers(url)
                async with session.get(url, headers=headers, ssl=False, timeout=15) as response:
                    if response.status != 200:
                        logger.info(f"توقف جلب الصفحات عند الصفحة {page_num} بسبب رمز الحالة: {response.status}")
                        break
                    html = await response.text()
            except Exception as e:
                logger.warning(f"فشل الاتصال بالصفحة {page_num}: {e}")
                break

            if page_num == 1:
                try:
                    soup = BeautifulSoup(html, "html.parser")
                    # 1. Parse high-res poster
                    img_el = soup.select_one(".anime-thumbnail img, .anime-info-right img, img.thumbnail")
                    if img_el:
                        img_src = img_el.get("src") or img_el.get("data-src")
                        if img_src and "default" not in img_src:
                            # Normalize any old domain references to current domain
                            for old_domain in ["witanime.pics", "witanime.you", "witanime.xyz"]:
                                img_src = img_src.replace(f"https://{old_domain}", f"https://{WITANIME_DOMAIN}")
                            poster_url = img_src
                            
                    # 2. Parse description/story
                    story_el = soup.select_one(".anime-story, p.anime-story, .story")
                    if story_el:
                        description = story_el.text.strip()
                        
                    # 3. Parse duration safely and defensively
                    duration_val = None
                    span_el = soup.find(lambda tag: tag.name == "span" and "مدة الحلقة" in tag.text)
                    if span_el:
                        parent = span_el.parent
                        if parent:
                            duration_val = parent.text.replace(span_el.text, "").replace(":", "").strip()
                    if not duration_val:
                        match_dur = re.search(r'<span>مدة الحلقة:</span>\s*([^<\n]+)', html)
                        if match_dur:
                            duration_val = match_dur.group(1).strip()
                    if not duration_val:
                        div_el = soup.find(lambda tag: tag.name == "div" and "مدة الحلقة:" in tag.text)
                        if div_el and len(div_el.text) < 150:
                            duration_val = div_el.text.replace("مدة الحلقة:", "").strip()
                            
                    if duration_val:
                        duration_val = " ".join(duration_val.split())
                        duration = duration_val[:90]
                except Exception as ex:
                    logger.warning(f"Failed to parse anime page metadata: {ex}")

            # Try encodedEpisodeData (base64 JSON) first, then processedEpisodeData (XOR encrypted)
            episodes_data = None
            encoded_match = re.search(r"var encodedEpisodeData = '([^']+)';", html)
            if encoded_match:
                try:
                    decoded_json = safe_b64decode(encoded_match.group(1)).decode("utf-8")
                    episodes_data = json.loads(decoded_json)
                    logger.info(f"Decoded {len(episodes_data)} episodes from encodedEpisodeData")
                except Exception:
                    logger.warning("Failed to decode encodedEpisodeData, trying processedEpisodeData...")
            
            if not episodes_data:
                match = re.search(r"var processedEpisodeData = '([^']+)';", html)
                if match:
                    episodes_data = decrypt_episodes(match.group(1))
                    
            if not episodes_data:
                if page_num == 1:
                    logger.info(f"لم يتم العثور على بيانات حلقات للأنمي {anime_slug}. يتم التعامل معه كفيلم فردي.")
                    return {
                        "episodes": [{
                            "ep_number": "1",
                            "play_url": f"https://{WITANIME_DOMAIN}/anime/{anime_slug}/"
                        }],
                        "poster_url": poster_url,
                        "description": description,
                        "duration": duration
                    }
                else:
                    break
                
            new_episodes_found = 0
            for ep in episodes_data:
                ep_num = str(ep.get("number"))
                play_url = ep.get("url")
                # Normalize any old domain references to current domain
                for old_domain in ["witanime.pics", "witanime.you", "witanime.xyz"]:
                    play_url = play_url.replace(f"https://{old_domain}", f"https://{WITANIME_DOMAIN}")
                
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
    return {
        "episodes": episodes,
        "poster_url": poster_url,
        "description": description,
        "duration": duration
    }

async def get_m3u8_from_embed(embed_url: str, session: aiohttp.ClientSession, referer: Optional[str] = None) -> Optional[str]:
    """Resolves and extracts .m3u8 master playlist or direct video file using custom player unpacker."""
    # mp4upload embed: parse video.src or Dean Edwards packed JS
    if "mp4upload.com" in embed_url or "mp4upload" in embed_url:
        try:
            logger.info(f"Resolving mp4upload embed: {embed_url}")
            headers = get_browser_headers(embed_url)
            html = ""
            if hasattr(session, 'get') and hasattr(session, 'impersonate'):
                resp = await session.get(embed_url, headers=headers, timeout=10)
                if resp.status_code == 200:
                    html = resp.text
            else:
                async with session.get(embed_url, headers=headers, allow_redirects=True, ssl=False, timeout=10) as resp:
                    if resp.status == 200:
                        html = await resp.text()

            if html:
                # 1. Unpack Dean Edwards JS if present
                script_match = re.search(r"eval\(function\(p,a,c,k,e,d\).*?\.split\(['\"]\|['\"]\)\)\)", html, re.DOTALL)
                if script_match:
                    unpacked = unpack_dean_edwards(script_match.group(0))
                    mp4_matches = re.findall(r'https?://[^\s"\']+\.mp4[^\s"\']*', unpacked)
                    if mp4_matches:
                        logger.info(f"Resolved mp4upload direct video from unpacked JS: {mp4_matches[0]}")
                        return mp4_matches[0]
                
                # 2. Search player.src({type: "video/mp4", src: "..."})
                src_match = re.search(r'player\.src\(\s*\{\s*type\s*:\s*["\']video/mp4["\']\s*,\s*src\s*:\s*["\'](https?://[^"\']+)["\']', html)
                if not src_match:
                    src_match = re.search(r'src\s*:\s*["\'](https?://[^"\']+\.mp4[^"\']*)["\']', html)
                if src_match:
                    logger.info(f"Resolved mp4upload direct video: {src_match.group(1)}")
                    return src_match.group(1)
        except Exception as e:
            logger.warning(f"Failed to resolve mp4upload embed: {e}")

    # my.mail.ru embed: parse videoSrc / metadata
    if "mail.ru" in embed_url or "my.mail.ru" in embed_url:
        try:
            logger.info(f"Resolving my.mail.ru embed: {embed_url}")
            headers = get_browser_headers(embed_url)
            html = ""
            if hasattr(session, 'get') and hasattr(session, 'impersonate'):
                resp = await session.get(embed_url, headers=headers, timeout=10)
                if resp.status_code == 200:
                    text_data = resp.text
            else:
                async with session.get(embed_url, headers=headers, allow_redirects=True, ssl=False, timeout=10) as resp:
                    if resp.status == 200:
                        text_data = await resp.text()

            if text_data:
                v_match = re.search(r'"videoSrc"\s*:\s*"([^"]+)"', text_data)
                if not v_match:
                    v_match = re.search(r'https?://[^"\']+\.mp4[^"\']*', text_data)
                if v_match:
                    url_res = v_match.group(1) if hasattr(v_match, 'group') and v_match.groups() else v_match.group(0)
                    if not url_res.startswith("http"):
                        url_res = f"https:{url_res}"
                    logger.info(f"Resolved my.mail.ru direct video: {url_res}")
                    return url_res
        except Exception as e:
            logger.warning(f"Failed to resolve my.mail.ru embed: {e}")

    # videa.hu embed: support XML decryption and direct static mp4/HLS links
    if "videa.hu" in embed_url or "videa" in embed_url:
        try:
            logger.info(f"Resolving videa.hu embed: {embed_url}")
            headers = get_browser_headers(embed_url)
            html = ""
            async with session.get(embed_url, headers=headers, ssl=False, timeout=10) as response:
                if response.status == 200:
                    html = await response.text()
                    # Check for direct static mp4 or HLS manifest in Videa HTML first
                    static_mp4s = re.findall(r'https?://static\.videa\.hu/[^"\']+\.mp4[^"\']*', html)
                    if not static_mp4s:
                        static_mp4s = re.findall(r'src=["\'](https?://[^"\']*videa[^"\']*\.mp4[^"\']*)["\']', html)
                    if static_mp4s:
                        logger.info(f"Resolved static videa.hu MP4 file: {static_mp4s[0]}")
                        return static_mp4s[0]
                        
                    hls_videa = re.findall(r'https?://[^"\']+\.m3u8[^"\']*', html)
                    if hls_videa:
                        logger.info(f"Resolved videa.hu HLS manifest: {hls_videa[0]}")
                        return hls_videa[0]

            # Extract video ID for XML decryption
            video_id_match = re.search(r'v=([a-zA-Z0-9]+)', embed_url)
            if not video_id_match:
                logger.warning("Failed to parse videa video ID")
                return None
            video_id = video_id_match.group(1)
            
            # Find _xt
            xt_match = re.search(r'_xt\s*=\s*"([^"]+)"', html)
            if not xt_match:
                logger.warning("Failed to find _xt nonce in Videa html")
                return None
            nonce = xt_match.group(1)
            
            _STATIC_SECRET = 'xHb0ZvME5q8CBcoQi6AngerDu3FGO9fkUlwPmLVY_RTzj2hJIS4NasXWKy1td7p'
            l = nonce[:32]
            s = nonce[32:]
            result = ''
            for i in range(32):
                idx = l[i]
                sec_idx = _STATIC_SECRET.index(idx)
                shift = sec_idx - 31
                char_idx = i - shift
                result += s[char_idx]
                
            import random
            import string
            random_seed = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
            t_param = result[:16]
            
            xml_url = f"https://videa.hu/player/xml?v={video_id}&_s={random_seed}&_t={t_param}"
            xml_headers = {
                "User-Agent": headers.get("User-Agent", get_random_user_agent()),
                "Referer": embed_url
            }
            
            async with session.get(xml_url, headers=xml_headers, ssl=False, timeout=10) as xml_resp:
                if xml_resp.status != 200:
                    logger.warning(f"Failed to fetch Videa XML: {xml_resp.status}")
                    return None
                body = await xml_resp.read()
                x_videa_xs = xml_resp.headers.get("x-videa-xs")
                
            if body.startswith(b'<?xml'):
                xml_text = body.decode('utf-8')
            else:
                if not x_videa_xs:
                    logger.warning("Missing x-videa-xs header for Videa decryption")
                    return None
                
                # RC4 decryption
                key = result[16:] + random_seed + x_videa_xs
                import struct
                res_bytes = b''
                key_len = len(key)
                S = list(range(256))
                j = 0
                for i in range(256):
                    j = (j + S[i] + ord(key[i % key_len])) % 256
                    S[i], S[j] = S[j], S[i]
                i = 0
                j = 0
                cipher_text = safe_b64decode(body)
                for m in range(len(cipher_text)):
                    i = (i + 1) % 256
                    j = (j + S[i]) % 256
                    S[i], S[j] = S[j], S[i]
                    k = S[(S[i] + S[j]) % 256]
                    res_bytes += struct.pack('B', k ^ cipher_text[m])
                try:
                    xml_text = res_bytes.decode('utf-8')
                except Exception:
                    xml_text = res_bytes.decode('latin-1')
                    
            import xml.etree.ElementTree as ET
            root = ET.fromstring(xml_text)
            video_sources = root.find('./video_sources')
            hash_values = root.find('./hash_values')
            
            videa_sources = {}
            if video_sources is not None:
                for source in video_sources.findall('./video_source'):
                    name = source.get('name')
                    exp = source.get('exp')
                    url = source.text
                    if not url:
                        continue
                    if not url.startswith("http"):
                        url = f"https:{url}"
                        
                    hash_value = None
                    if hash_values is not None:
                        hash_el = hash_values.find(f'hash_value_{name}')
                        if hash_el is not None:
                            hash_value = hash_el.text
                            
                    if hash_value and exp:
                        url = f"{url}?md5={hash_value}&expires={exp}"
                        
                    q_name = normalize_quality_name(name)
                    videa_sources[q_name] = url
                    
            if videa_sources:
                logger.info(f"Resolved videa.hu qualities: {list(videa_sources.keys())}")
                return json.dumps(videa_sources)
                
        except Exception as e:
            logger.exception(f"Failed to decrypt/resolve Videa: {e}")
        return None

    # ok.ru embed: parse embedded JSON metadata for direct video URLs or hlsManifestUrl
    if "ok.ru" in embed_url:
        try:
            logger.info(f"Resolving ok.ru embed: {embed_url}")
            headers = get_browser_headers(embed_url)
            text = ""
            if hasattr(session, 'get') and hasattr(session, 'impersonate'):
                resp = await session.get(embed_url, headers=headers, timeout=10)
                if resp.status_code == 200:
                    text = resp.text
            else:
                async with session.get(embed_url, headers=headers, allow_redirects=True, ssl=False, timeout=10) as resp:
                    if resp.status == 200:
                        text = await resp.text()

            if text:
                import html as html_lib
                text = html_lib.unescape(text)
                ok_qualities = {}

                # Extract data-options or metadata json attribute
                meta_matches = re.findall(r'data-options="([^"]+)"', text)
                for meta_raw in meta_matches:
                    clean_raw = meta_raw.replace('&quot;', '"').replace('\\"', '"').replace('\\u0026', '&')
                    try:
                        meta_json = json.loads(clean_raw)
                        meta_obj = meta_json.get("flashvars", meta_json)
                        if isinstance(meta_obj, dict) and "metadata" in meta_obj:
                            meta_inner = json.loads(meta_obj["metadata"]) if isinstance(meta_obj["metadata"], str) else meta_obj["metadata"]
                            videos = meta_inner.get("videos", [])
                            for v in videos:
                                v_url = v.get("url")
                                v_name = str(v.get("name", "")).lower()
                                if v_url:
                                    if "full" in v_name or "1080" in v_name:
                                        ok_qualities["1080p"] = v_url
                                    elif "hd" in v_name or "720" in v_name:
                                        ok_qualities["720p"] = v_url
                                    elif "sd" in v_name or "480" in v_name:
                                        ok_qualities["480p"] = v_url
                                    elif "low" in v_name or "360" in v_name:
                                        ok_qualities["360p"] = v_url
                                    elif "lowest" in v_name or "240" in v_name:
                                        ok_qualities["240p"] = v_url
                                    else:
                                        ok_qualities["720p"] = v_url
                    except Exception:
                        pass

                if ok_qualities:
                    logger.info(f"Resolved ok.ru qualities: {list(ok_qualities.keys())}")
                    return json.dumps(ok_qualities)

                # Direct HLS manifest search
                hls_match = re.search(r'hlsManifestUrl[^\s"\']*"\s*:\s*"([^"]+)"', text)
                if hls_match:
                    hls_url = hls_match.group(1).replace('\\u0026', '&').replace('\\/', '/')
                    logger.info(f"Resolved ok.ru HLS manifest: {hls_url}")
                    return hls_url

                # Direct video URLs regex pattern (https://vd*.okcdn.ru/... or vd*.mycdn.me/...)
                video_matches = re.findall(r'"url"\s*:\s*"(https?://[^"\']+(?:okcdn|mycdn|vd)[^"\']*)"', text)
                if video_matches:
                    best_url = video_matches[-1].replace('\\u0026', '&').replace('\\/', '/')
                    logger.info(f"Resolved ok.ru direct video: {best_url}")
                    return best_url
        except Exception as e:
            logger.warning(f"Failed to resolve ok.ru embed: {e}")
        return None

    # yonaplay / mid.yonaplay.net embed: resolve hash embeds and aggregator options
    if "yonaplay.net" in embed_url or "yonaplay" in embed_url:
        try:
            ref = referer or f"https://{WITANIME_DOMAIN}/"
            headers = {"User-Agent": get_random_user_agent(), "Referer": ref}
            logger.info(f"Resolving yonaplay aggregator from: {embed_url} with referer: {ref}")
            
            async with session.get(embed_url, headers=headers, ssl=False, timeout=10) as resp:
                if resp.status == 200:
                    html = await resp.text()

                    # 1. Check for iframe embedded players in yonaplay HTML
                    iframe_matches = re.findall(r'<iframe[^>]+src=["\']([^"\']+)["\']', html, re.IGNORECASE)
                    for iframe_url in iframe_matches:
                        if not iframe_url.startswith("http"):
                            iframe_url = urljoin(embed_url, iframe_url)
                        logger.info(f"Found yonaplay embedded iframe: {iframe_url}")
                        res_m3u8 = await get_m3u8_from_embed(iframe_url, session, referer=embed_url)
                        if res_m3u8:
                            return res_m3u8

                    # 2. Check for direct .m3u8 or .mp4 file links in script tags
                    m3u8_direct = re.search(r'file\s*:\s*["\'](https?://[^"\']+\.m3u8[^"\']*)["\']', html)
                    if not m3u8_direct:
                        m3u8_direct = re.search(r'["\'](https?://[^"\']+\.m3u8[^"\']*)["\']', html)
                    if m3u8_direct and m3u8_direct.group(1).startswith("http"):
                        logger.info(f"Resolved direct m3u8 from yonaplay: {m3u8_direct.group(1)}")
                        return m3u8_direct.group(1)

                    # 3. Find all go_to_player('...') Base64 strings
                    b64_matches = re.findall(r"go_to_player\(['\"]([a-zA-Z0-9+/=]+)['\"]\)", html)
                    logger.info(f"yonaplay found {len(b64_matches)} player options")
                    
                    for b64_str in b64_matches:
                        try:
                            decoded_url = safe_b64decode(b64_str).decode("utf-8")
                            logger.info(f"Decoded yonaplay player option: {decoded_url}")
                            
                            if "dotplay.net" in decoded_url:
                                match_code = re.search(r"/embed/([a-zA-Z0-9]+)", decoded_url)
                                if match_code:
                                    code = match_code.group(1)
                                    api_url = f"https://dotplay.net/api.php?code={code}"
                                    api_headers = {
                                        "User-Agent": get_random_user_agent(),
                                        "Referer": decoded_url,
                                        "Accept": "application/json"
                                    }
                                    logger.info(f"Calling dotplay API: {api_url}")
                                    async with session.get(api_url, headers=api_headers, ssl=False, timeout=10) as api_resp:
                                        if api_resp.status == 200:
                                            data = await api_resp.json()
                                            if data.get("success") and data.get("video_url"):
                                                dec_url = safe_b64decode(data["video_url"]).decode("utf-8").split("|")[0]
                                                logger.info(f"Resolved video URL from dotplay: {dec_url}")
                                                return dec_url
                            elif "http" in decoded_url:
                                res_m3u8 = await get_m3u8_from_embed(decoded_url, session, referer=embed_url)
                                if res_m3u8:
                                    return res_m3u8
                        except Exception as e:
                            logger.warning(f"Failed to resolve yonaplay option {b64_str}: {e}")
        except Exception as e:
            logger.exception(f"Error resolving yonaplay: {e}")
        return None

    headers = get_browser_headers(embed_url)
    
    # Try multiple known mirror player domains if it's hglink.to / hgcloud.to or Streamwish
    target_urls = [embed_url]
    if "hglink.to" in embed_url or "hgcloud.to" in embed_url or "hanerix.com" in embed_url or "masukestin.com" in embed_url:
        try:
            video_id = None
            for prefix in ["/e/", "/watch/", "/embed/"]:
                if prefix in embed_url:
                    video_id = embed_url.split(prefix)[1].split("?")[0].strip("/")
                    break
            if video_id:
                target_urls = [
                    f"https://hanerix.com/e/{video_id}",
                    f"https://masukestin.com/e/{video_id}",
                    f"https://hglink.to/e/{video_id}",
                    f"https://hgcloud.to/e/{video_id}"
                ]
        except Exception:
            pass
            
    # Handle Universal Streamwish/Playerwish mirrors (matching *wish* or clone player domains)
    wish_domains = ["wish", "streamwish", "hlswish", "stwish", "ninjastr", "awish", "wishembed", "wishfast", "closwish", "cybervynx", "swdyu", "flaswish", "sfastwish", "obeywish", "jodwish", "embedwish", "cdnwish", "strwish", "iplayerhls", "suzihazarpc", "filelions"]
    if "wish" in embed_url.lower() or any(d in embed_url.lower() for d in wish_domains):
        video_id = None
        for path_prefix in ["/e/", "/watch/", "/embed/", "/v/"]:
            if path_prefix in embed_url:
                try:
                    video_id = embed_url.split(path_prefix)[1].split("?")[0].strip("/")
                    break
                except Exception:
                    pass
        if video_id:
            # Construct fallback URLs using multiple active player wish domains
            target_urls = [
                f"https://hlswish.com/e/{video_id}",
                f"https://swdyu.com/e/{video_id}",
                f"https://flaswish.com/e/{video_id}",
                f"https://sfastwish.com/e/{video_id}",
                f"https://obeywish.com/e/{video_id}",
                f"https://jodwish.com/e/{video_id}",
                f"https://embedwish.com/e/{video_id}",
                f"https://cdnwish.com/e/{video_id}",
                f"https://strwish.xyz/e/{video_id}",
                f"https://awish.pro/e/{video_id}",
                f"https://streamwish.to/e/{video_id}",
                embed_url # Original URL fallback
            ]
        
    for url in target_urls:
        logger.info(f"Attempting to resolve embed playlist from: {url}")
        try:
            async with session.get(url, headers=get_browser_headers(url), ssl=False, timeout=10) as response:
                if response.status != 200:
                    continue
                text = await response.text()
                text = text.replace("\\/", "/")
                
                # Check for direct mp4 match first
                mp4_match = re.search(r'src\s*:\s*["\'](https?://[^"\']+\.mp4[^"\']*)["\']', text)
                if not mp4_match:
                    mp4_match = re.search(r'["\']?file["\']?\s*:\s*["\'](https?://[^"\']+\.mp4[^"\']*)["\']', text)
                if mp4_match:
                    mp4_url = mp4_match.group(1)
                    logger.info(f"Resolved direct MP4 stream: {mp4_url}")
                    return mp4_url
                
                # Check for Dean Edwards packed JS script in Playerwish / Streamwish layout
                script_match = re.search(r"eval\(function\(p,a,c,k,e,d\).*?\.split\(['\"]\|['\"]\)\)\)", text, re.DOTALL)
                if script_match:
                    unpacked = unpack_dean_edwards(script_match.group(0))
                    m3u8_matches = re.findall(r'https?://[^\s"\']+\.m3u8[^\s"\']*', unpacked)
                    if m3u8_matches:
                        m3u8_url = m3u8_matches[0]
                        logger.info(f"Resolved streamwish mirror HLS stream from unpacked JS: {m3u8_url}")
                        return m3u8_url
                    direct_file = re.search(r'file\s*:\s*["\'](https?://[^"\']+)["\']', unpacked)
                    if direct_file:
                        logger.info(f"Resolved streamwish direct file from unpacked JS: {direct_file.group(1)}")
                        return direct_file.group(1)
                
                # Regular regex search inside non-packed body
                match = re.search(r'const\s+src\s*=\s*["\']([^"\']+\.m3u8[^"\']*)["\']', text)
                if not match:
                    match = re.search(r'src\s*:\s*["\']([^"\']+\.m3u8[^"\']*)["\']', text)
                if not match:
                    match = re.search(r'["\']([^"\']+\.m3u8[^"\']*)["\']', text)
                if match:
                    m3u8_url = match.group(1)
                    if m3u8_url.startswith('http') and len(m3u8_url) < 2000:
                        logger.info(f"Resolved master .m3u8 playlist: {m3u8_url}")
                        return m3u8_url
                    else:
                        logger.warning(f"Skipping invalid m3u8 match (len={len(m3u8_url)}): not a valid URL")
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
                play_url = play_url.replace("https://witanime.you", f"https://{WITANIME_DOMAIN}")
                
            html = await get_html(play_url, session)
            
            # Find server labels/names inside DOM
            soup = BeautifulSoup(html, "html.parser")
            
            # Try a broader and more resilient list of selectors for server elements
            servers = []
            for sel in [
                "#episode-servers li", ".episode-servers li", "ul.servers-list li", ".servers-list li", 
                "#watch-servers li", "li.server", "#episode-servers a", ".episode-servers a", 
                "#watch-servers a", "ul.servers-list a", ".servers-list a",
                ".server-list li", "#servers-list li", "div.watch-servers li", ".tab-content .server-item", "ul li[data-server]"
            ]:
                found = soup.select(sel)
                if found:
                    servers = found
                    break
            
            server_names = [s.text.strip().lower() for s in servers]
            
            # Extract player registry keys
            zx_match = re.search(r'var _zX="([^"]+)"', html)
            zk_match = re.search(r'var _zK="([^"]+)"', html)
            
            if not zx_match or not zk_match:
                logger.warning("Failed to locate player registries (_zX / _zK) on watch page")
                return {}
                
            resources = json.loads(safe_b64decode(zx_match.group(1)).decode("utf-8"))
            configs = json.loads(safe_b64decode(zk_match.group(1)).decode("utf-8"))
            
            resolved_links = {}
            hls_indices = []
            other_indices = []
            direct_indices = []
            
            for idx, (res, conf) in enumerate(zip(resources, configs)):
                s_name = server_names[idx] if idx < len(server_names) else ""
                # Prioritize active HLS streaming mirrors at the top of the queue
                if any(x in s_name for x in ["streamwish", "yona", "yonaplay", "videa", "hglink", "soraplay", "sorastream", "hanerix"]):
                    hls_indices.append(idx)
                # Push direct file hosts to the absolute bottom of the queue
                elif "mp4upload" in s_name or "yourupload" in s_name:
                    direct_indices.append(idx)
                else:
                    other_indices.append(idx)
                    
            for idx in hls_indices + other_indices + direct_indices:
                res = resources[idx]
                conf = configs[idx]
                s_name = server_names[idx] if idx < len(server_names) else ""
                embed_url = decrypt_resource(res, conf)
                if embed_url:
                    m3u8_master = await get_m3u8_from_embed(embed_url, session, referer=play_url)
                    if m3u8_master:
                        if m3u8_master.startswith("{"):
                            try:
                                qualities = json.loads(m3u8_master)
                                resolved_links.update(qualities)
                            except Exception:
                                pass
                        elif ".m3u8" in m3u8_master:
                            qualities = await parse_m3u8_qualities(m3u8_master, session)
                            resolved_links.update(qualities)
                        else:
                            # Direct MP4 file link resolved from mirror!
                            q_name = normalize_quality_name(s_name) if s_name else "480p"
                            if q_name not in ["1080p", "720p", "480p", "360p", "240p"]:
                                q_name = "480p"
                            resolved_links[q_name] = m3u8_master
                            
            if not resolved_links:
                logger.info("HLS/Embed parsing yielded 0 links. Scraping fallback download table buttons on watch page...")
                download_btns = soup.select(".download-links a, table.download-table a, a.download-link, .download-item a, .download-list a")
                if not download_btns:
                    download_btns = soup.find_all("a", href=lambda h: h and ("download" in str(h).lower() or "mp4upload" in str(h).lower() or "upload" in str(h).lower()))
                    
                for a in download_btns:
                    href = a.get("href")
                    if href and href.startswith("http"):
                        label = a.text.strip().lower()
                        q_name = normalize_quality_name(label)
                        if q_name not in ["1080p", "720p", "480p", "360p", "240p"]:
                            if "1080" in href or "fhd" in label:
                                q_name = "1080p"
                            elif "720" in href or "hd" in label:
                                q_name = "720p"
                            elif "360" in href or "sd" in label:
                                q_name = "360p"
                            else:
                                q_name = "480p"

                        # Follow shortlink redirects (e.g. go.witanime.life) to get raw stream/download link
                        final_url = href
                        if "go.witanime" in href or "/go/" in href or "redirect" in href or "short" in href:
                            try:
                                logger.info(f"Following shortlink redirect for fallback download link: {href}")
                                if hasattr(session, 'get') and hasattr(session, 'impersonate'):
                                    resp = await session.get(href, headers=get_browser_headers(href), timeout=8)
                                    if resp.url:
                                        final_url = str(resp.url)
                                else:
                                    async with session.get(href, headers=get_browser_headers(href), allow_redirects=True, ssl=False, timeout=8) as resp:
                                        final_url = str(resp.url)
                                logger.info(f"Resolved shortlink final destination: {final_url}")
                            except Exception as ex:
                                logger.warning(f"Failed resolving shortlink redirect for {href}: {ex}")

                        if q_name not in resolved_links:
                            resolved_links[q_name] = final_url
                            
            if not resolved_links:
                logger.warning("Failed to parse working HLS streams or direct video files from embed servers or download table")
                return {}
                
            logger.info(f"Resolved {len(resolved_links)} download link qualities: {list(resolved_links.keys())}")
            return resolved_links
        except Exception:
            logger.exception("Error in process while scraping download links")
            return {}
