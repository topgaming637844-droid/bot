import aiohttp
from typing import Any, Optional
from aiohttp_socks import ProxyConnector
from urllib.parse import quote
from config import config
from app.utils.logging_config import logger

async def translate_to_english(text: str) -> Optional[str]:
    """Translates Arabic text to English using Google Translate free API."""
    # Check if text contains Arabic characters (Unicode block 0600-06FF)
    if not any(ord(c) >= 0x0600 and ord(c) <= 0x06FF for c in text):
        return None
        
    url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl=en&dt=t&q={quote(text)}"
    try:
        # Direct connection for translation to ensure fast and reliable execution
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=5) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    translated = data[0][0][0]
                    logger.info(f"Translated Arabic query '{text}' to '{translated}' using Google Translate API")
                    return translated
    except Exception as e:
        logger.warning(f"Failed to translate query to English: {e}")
    return None

async def translate_to_arabic(text: str) -> Optional[str]:
    """Translates English text to Arabic using Google Translate free API."""
    if not text or text.strip() == "" or text == "لا يوجد":
        return None
    url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl=ar&dt=t&q={quote(text)}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=5) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    parts = []
                    for sentence in data[0]:
                        if sentence and len(sentence) > 0 and sentence[0]:
                            parts.append(sentence[0])
                    translated = "".join(parts)
                    return translated
    except Exception as e:
        logger.warning(f"Failed to translate description to Arabic: {e}")
    return None

import time

SEARCH_MEMORY_CACHE: dict[str, tuple[float, list[dict[str, Any]]]] = {}
CACHE_TTL = 3600  # 1 hour in-memory cache for 0-second instant search resolution

# Optimized slim GraphQL query for searching anime directly
MEDIA_QUERY = """
query ($search: String) {
  Page(page: 1, perPage: 8) {
    media(search: $search, type: ANIME) {
      id
      title {
        romaji
        english
      }
      synonyms
      description
      coverImage {
        large
      }
      duration
    }
  }
}
"""

# Optimized slim GraphQL query for searching anime via character names
CHARACTER_QUERY = """
query ($search: String) {
  Page(page: 1, perPage: 3) {
    characters(search: $search) {
      media(type: ANIME, perPage: 3) {
        nodes {
          id
          title {
            romaji
            english
          }
          synonyms
          description
          coverImage {
            large
          }
          duration
        }
      }
    }
  }
}
"""

def get_connector() -> Optional[ProxyConnector]:
    """Helper to return proxy connector if PROXY_URL is configured."""
    if config.PROXY_URL:
        try:
            return ProxyConnector.from_url(config.PROXY_URL)
        except Exception:
            logger.exception("Error in process while initializing proxy connector")
    return None

async def search_anilist(query: str) -> list[dict[str, Any]]:
    """
    Search Cloud Index API.
    Resolves typos, Franco-Arabic, and character names into official titles with zero-second memory cache.
    """
    clean_key = query.strip().lower()
    if clean_key in SEARCH_MEMORY_CACHE:
        timestamp, cached_res = SEARCH_MEMORY_CACHE[clean_key]
        if time.time() - timestamp < CACHE_TTL:
            logger.info(f"Zero-second Memory Cache Hit for search query: '{query}'")
            return cached_res

    # Translate Arabic queries to English first to ensure matching works
    translated_query = await translate_to_english(query)
    search_query = translated_query if translated_query else query
    
    logger.info(f"Starting cloud index search for query: {search_query} (original: {query})")
    url = "https://graphql.anilist.co"
    
    # Try importing curl_cffi
    try:
        from curl_cffi.requests import AsyncSession as CurlAsyncSession
        curl_cffi_available = True
    except ImportError:
        curl_cffi_available = False
        CurlAsyncSession = None

    try:
        from app.utils.user_agents import get_random_user_agent
        ua = get_random_user_agent()
    except Exception:
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Origin": "https://anilist.co",
        "Referer": "https://anilist.co/",
        "User-Agent": ua
    }
    
    for attempt in range(2):
        proxies = {"http": config.PROXY_URL, "https": config.PROXY_URL} if (config.PROXY_URL and attempt == 0) else None
        if attempt > 0:
            logger.info("Retrying search directly (bypassing proxy)...")
            
        payload = {
            "query": MEDIA_QUERY,
            "variables": {"search": search_query}
        }
        results = []
        
        try:
            if curl_cffi_available and CurlAsyncSession:
                async with CurlAsyncSession(impersonate="chrome120", proxies=proxies) as session:
                    logger.info("Scraping page: https://graphql.anilist.co (Direct Media Query via curl_cffi)")
                    response = await session.post(url, json=payload, headers=headers, timeout=10)
                    if response.status_code == 200:
                        data = response.json()
                        media_list = data.get("data", {}).get("Page", {}).get("media", [])
                        for media in media_list:
                            results.append(await parse_media_node(media))
                    else:
                        logger.warning(f"AniList returned status {response.status_code}")
                        if response.status_code == 403:
                            logger.warning("AniList returned 403 Forbidden. Silently failing over to local WitAnime scraper.")
                            return []
                        raise Exception(f"AniList status {response.status_code}")
            else:
                connector = get_connector() if attempt == 0 else None
                async with aiohttp.ClientSession(connector=connector) as session:
                    logger.info("Scraping page: https://graphql.anilist.co (Direct Media Query via aiohttp)")
                    async with session.post(url, json=payload, headers=headers, timeout=10) as response:
                        if response.status == 200:
                            data = await response.json()
                            media_list = data.get("data", {}).get("Page", {}).get("media", [])
                            for media in media_list:
                                results.append(await parse_media_node(media))
                        else:
                            logger.warning(f"AniList returned status {response.status}")
                            if response.status == 403:
                                logger.warning("AniList returned 403 Forbidden. Silently failing over to local WitAnime scraper.")
                                return []
                            raise Exception(f"AniList status {response.status}")
                                
            # 2. If no direct media found, fallback to character search
            if not results:
                logger.info(f"Direct media search returned 0 results. Falling back to character query for: {query}")
                payload_char = {
                    "query": CHARACTER_QUERY,
                    "variables": {"search": query}
                }
                if curl_cffi_available and CurlAsyncSession:
                    async with CurlAsyncSession(impersonate="chrome120", proxies=proxies) as session:
                        logger.info("Scraping page: https://graphql.anilist.co (Character Query via curl_cffi)")
                        response = await session.post(url, json=payload_char, headers=headers, timeout=10)
                        if response.status_code == 200:
                            data = response.json()
                            characters = data.get("data", {}).get("Page", {}).get("characters", [])
                            seen_ids = set()
                            for char in characters:
                                media_nodes = char.get("media", {}).get("nodes", [])
                                for media in media_nodes:
                                    if media["id"] not in seen_ids:
                                        results.append(await parse_media_node(media))
                                        seen_ids.add(media["id"])
                        else:
                            logger.warning(f"AniList character search returned status {response.status_code}")
                            if response.status_code == 403:
                                logger.warning("AniList returned 403 Forbidden on character search. Silently failing over to local WitAnime scraper.")
                                return []
                else:
                    connector = get_connector() if attempt == 0 else None
                    async with aiohttp.ClientSession(connector=connector) as session:
                        logger.info("Scraping page: https://graphql.anilist.co (Character Query via aiohttp)")
                        async with session.post(url, json=payload_char, headers=headers, timeout=10) as response:
                            if response.status == 200:
                                data = await response.json()
                                characters = data.get("data", {}).get("Page", {}).get("characters", [])
                                seen_ids = set()
                                for char in characters:
                                    media_nodes = char.get("media", {}).get("nodes", [])
                                    for media in media_nodes:
                                        if media["id"] not in seen_ids:
                                            results.append(await parse_media_node(media))
                                            seen_ids.add(media["id"])
                            else:
                                logger.warning(f"AniList character search returned status {response.status}")
                                if response.status == 403:
                                    logger.warning("AniList returned 403 Forbidden on character search. Silently failing over to local WitAnime scraper.")
                                    return []
                                
            logger.info(f"Cloud index search returned {len(results)} normalized titles.")
            if results:
                SEARCH_MEMORY_CACHE[clean_key] = (time.time(), results)
            return results
            
        except Exception as e:
            logger.warning(f"Attempt {attempt} failed in search_anilist: {e}")
            if attempt == 0:
                continue
            break
            
    return []

async def parse_media_node(media: dict[str, Any]) -> dict[str, Any]:
    """Extracts and normalizes media details from a GraphQL node."""
    title_data = media.get("title", {})
    title_english = title_data.get("english")
    title_romaji = title_data.get("romaji", "Unknown Title")
    
    # Clean HTML tags from AniList description
    description = media.get("description", "")
    if description:
        import re
        import html
        description = re.sub(r'<[^>]*>', '', description)
        description = html.unescape(description)
        
    cover_image = media.get("coverImage", {})
    image_url = cover_image.get("extraLarge") or cover_image.get("large")
    
    raw_duration = media.get("duration")
    duration = f"{raw_duration} دقيقة" if raw_duration else None
    
    # Extract synonyms (alternative titles) for fallback search
    synonyms = media.get("synonyms", []) or []
    # Filter out empty strings and duplicates
    synonyms = [s.strip() for s in synonyms if s and s.strip()]

    return {
        "anilist_id": media.get("id"),
        "title_english": title_english,
        "title_romaji": title_romaji,
        "description": description,
        "image_url": image_url,
        "duration": duration,
        "episodes_count": media.get("episodes"),
        "synonyms": synonyms,
    }
