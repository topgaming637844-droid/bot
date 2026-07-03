import aiohttp
from typing import List, Dict, Any, Optional
from config import config
from aiohttp_socks import ProxyConnector
from app.utils.logging_config import logger

# GraphQL query for searching anime directly
MEDIA_QUERY = """
query ($search: String) {
  Page (perPage: 5) {
    media (search: $search, type: ANIME) {
      id
      title {
        romaji
        english
        native
      }
      description
      coverImage {
        large
      }
      synonyms
      episodes
    }
  }
}
"""

# GraphQL query for searching anime via character names
CHARACTER_QUERY = """
query ($search: String) {
  Page (perPage: 3) {
    characters (search: $search) {
      media (type: ANIME, perPage: 3) {
        nodes {
          id
          title {
            romaji
            english
            native
          }
          description
          coverImage {
            large
          }
          synonyms
          episodes
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

async def search_anilist(query: str) -> List[Dict[str, Any]]:
    """
    Search AniList GraphQL API.
    Resolves typos, Franco-Arabic, and character names into official titles.
    """
    logger.info(f"Starting search on AniList for query: {query}")
    url = "https://graphql.anilist.co"
    
    for attempt in range(2):
        connector = get_connector()
        if attempt > 0:
            logger.info("Retrying AniList search directly (bypassing proxy)...")
            
        payload = {
            "query": MEDIA_QUERY,
            "variables": {"search": query}
        }
        results = []
        
        try:
            async with aiohttp.ClientSession(connector=connector) as session:
                try:
                    logger.info("Scraping page: https://graphql.anilist.co (Direct Media Query)")
                    async with session.post(url, json=payload, timeout=10) as response:
                        if response.status == 200:
                            data = await response.json()
                            media_list = data.get("data", {}).get("Page", {}).get("media", [])
                            for media in media_list:
                                results.append(parse_media_node(media))
                        else:
                            logger.error(f"Error in process: AniList media query returned status {response.status}")
                except Exception as e:
                    if connector and ("proxy" in str(e).lower() or "socks" in str(e).lower() or "authentication failure" in str(e).lower()):
                        logger.warning(f"Proxy failure during AniList media query: {e}. Disabling proxy.")
                        config.PROXY_URL = None
                        raise e
                    logger.exception("Error in process while querying AniList media API")
                    
                # 2. If no direct media found, fallback to character search
                if not results:
                    logger.info(f"Direct media search returned 0 results. Falling back to character query for: {query}")
                    payload_char = {
                        "query": CHARACTER_QUERY,
                        "variables": {"search": query}
                    }
                    try:
                        logger.info("Scraping page: https://graphql.anilist.co (Character Query)")
                        async with session.post(url, json=payload_char, timeout=10) as response:
                            if response.status == 200:
                                data = await response.json()
                                characters = data.get("data", {}).get("Page", {}).get("characters", [])
                                seen_ids = set()
                                for char in characters:
                                    media_nodes = char.get("media", {}).get("nodes", [])
                                    for media in media_nodes:
                                        if media["id"] not in seen_ids:
                                            results.append(parse_media_node(media))
                                            seen_ids.add(media["id"])
                            else:
                                logger.error(f"Error in process: AniList character query returned status {response.status}")
                    except Exception as e:
                        if connector and ("proxy" in str(e).lower() or "socks" in str(e).lower() or "authentication failure" in str(e).lower()):
                            logger.warning(f"Proxy failure during AniList character query: {e}. Disabling proxy.")
                            config.PROXY_URL = None
                            raise e
                        logger.exception("Error in process while querying AniList characters API")
                        
            logger.info(f"AniList search returned {len(results)} normalized titles.")
            return results
            
        except Exception:
            if config.PROXY_URL is None and attempt == 0:
                continue
            break
            
    return []

def parse_media_node(media: Dict[str, Any]) -> Dict[str, Any]:
    """Extracts and normalizes media details from a GraphQL node."""
    title_data = media.get("title", {})
    title_english = title_data.get("english")
    title_romaji = title_data.get("romaji", "Unknown Title")
    
    # Clean HTML tags from AniList description
    description = media.get("description", "")
    if description:
        import re
        description = re.sub(r'<[^>]*>', '', description)
        
    return {
        "anilist_id": media.get("id"),
        "title_english": title_english,
        "title_romaji": title_romaji,
        "description": description,
        "image_url": media.get("coverImage", {}).get("large"),
        "episodes_count": media.get("episodes"),
    }
