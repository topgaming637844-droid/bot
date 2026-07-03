import aiohttp
from typing import List, Dict, Any, Optional
from config import config
from aiohttp_socks import ProxyConnector

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
        except Exception as e:
            print(f"Error initializing proxy connector: {e}")
    return None

async def search_anilist(query: str) -> List[Dict[str, Any]]:
    """
    Search AniList GraphQL API.
    Resolves typos, Franco-Arabic, and character names into official titles.
    """
    url = "https://graphql.anilist.co"
    connector = get_connector()
    
    # 1. Try direct media search
    payload = {
        "query": MEDIA_QUERY,
        "variables": {"search": query}
    }
    
    results = []
    
    async with aiohttp.ClientSession(connector=connector) as session:
        try:
            async with session.post(url, json=payload, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    media_list = data.get("data", {}).get("Page", {}).get("media", [])
                    for media in media_list:
                        results.append(parse_media_node(media))
        except Exception as e:
            print(f"Error querying AniList media API: {e}")
            
        # 2. If no direct media found, fallback to character search
        if not results:
            payload = {
                "query": CHARACTER_QUERY,
                "variables": {"search": query}
            }
            try:
                async with session.post(url, json=payload, timeout=10) as response:
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
            except Exception as e:
                print(f"Error querying AniList characters API: {e}")
                
    return results

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
