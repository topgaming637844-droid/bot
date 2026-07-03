import re
import aiohttp
from bs4 import BeautifulSoup
from typing import List, Dict, Any, Optional
from config import config
from app.utils.user_agents import get_random_user_agent
from app.services.anilist import get_connector

class ScraperError(Exception):
    """Base exception for scraping operations."""
    pass

async def get_html(url: str, session: aiohttp.ClientSession) -> str:
    """Fetches HTML content with custom headers and optional proxy."""
    headers = {"User-Agent": get_random_user_agent()}
    try:
        async with session.get(url, headers=headers, timeout=15) as response:
            if response.status == 200:
                return await response.text()
            raise ScraperError(f"HTTP error {response.status} fetching {url}")
    except Exception as e:
        if not isinstance(e, ScraperError):
            raise ScraperError(f"Connection failed: {e}") from e
        raise

async def search_anime_scraper(title: str) -> List[Dict[str, Any]]:
    """
    Searches for anime on Gogoanime.
    Returns a list of dictionaries with title and slug.
    """
    if config.MOCK_MODE:
        # Mock search results for offline validation
        print("[MOCK MODE] Simulating search result on Gogoanime.")
        return [
            {
                "title": f"{title} (TV)",
                "slug": "one-piece-tv" if "piece" in title.lower() or "luffy" in title.lower() else "mock-anime-slug"
            }
        ]

    search_url = f"{config.GOGOANIME_BASE_URL}/search.html?keyword={title}"
    connector = get_connector()
    
    async with aiohttp.ClientSession(connector=connector) as session:
        try:
            html = await get_html(search_url, session)
            soup = BeautifulSoup(html, "html.parser")
            items = soup.select("ul.items li")
            
            results = []
            for item in items:
                link_el = item.select_one("p.name a")
                if link_el:
                    title_text = link_el.get("title") or link_el.text.strip()
                    href = link_el.get("href", "")
                    # Extract slug from href (e.g. /category/one-piece -> one-piece)
                    slug = href.replace("/category/", "") if "/category/" in href else href.strip("/")
                    results.append({"title": title_text, "slug": slug})
            return results
        except Exception as e:
            print(f"Error scraping search results: {e}")
            return []

async def get_episodes_scraper(anime_slug: str) -> List[Dict[str, Any]]:
    """
    Retrieves the list of episodes for an anime slug.
    """
    if config.MOCK_MODE:
        # Mock 12 episodes for testing
        print("[MOCK MODE] Generating mock episodes list.")
        return [
            {
                "ep_number": str(i),
                "play_url": f"https://mock-play-page.com/{anime_slug}-episode-{i}"
            }
            for i in range(1, 13)
        ]

    anime_url = f"{config.GOGOANIME_BASE_URL}/category/{anime_slug}"
    connector = get_connector()
    
    async with aiohttp.ClientSession(connector=connector) as session:
        try:
            html = await get_html(anime_url, session)
            soup = BeautifulSoup(html, "html.parser")
            
            # Find the movie ID required for the episodes list AJAX call
            movie_id_input = soup.select_one("input#movie_id")
            if not movie_id_input:
                raise ScraperError("Failed to find movie ID input on category page")
                
            movie_id = movie_id_input.get("value")
            
            # Gogoanime loads episodes via an AJAX request
            ajax_url = f"https://ajax.gogo-load.com/ajax/load-list-episode?ep_start=0&ep_end=3000&id={movie_id}&default_ep=0&alias={anime_slug}"
            
            ajax_html = await get_html(ajax_url, session)
            ajax_soup = BeautifulSoup(ajax_html, "html.parser")
            
            episode_links = ajax_soup.select("ul#episode_related li a")
            episodes = []
            
            # The list returned from AJAX is usually from newest to oldest
            for link in reversed(episode_links):
                href = link.get("href", "").strip()
                # Parse episode number from the link child div
                name_div = link.select_one("div.name")
                ep_text = name_div.text.replace("EP", "").strip() if name_div else ""
                if not ep_text:
                    # Fallback regex parse from href
                    match = re.search(r"-episode-(\d+(\.\d+)?)$", href)
                    ep_text = match.group(1) if match else "1"
                
                full_play_url = f"{config.GOGOANIME_BASE_URL}{href}" if href.startswith("/") else href
                episodes.append({
                    "ep_number": ep_text,
                    "play_url": full_play_url
                })
                
            return episodes
        except Exception as e:
            print(f"Error scraping episodes list: {e}")
            return []

async def get_download_links_scraper(play_url: str) -> Dict[str, str]:
    """
    Parses the episode play page, extracts the streaming player iframe,
    navigates to the download mirrors page, and resolves direct video files.
    """
    if config.MOCK_MODE:
        # Mock video files of different sizes for validation.
        # Downloader will intercept these URLs to mock Content-Length values.
        print("[MOCK MODE] Returning mock direct download video paths.")
        return {
            "1080p": "https://test-videos.co.uk/vids/bigbuckbunny/mp4/h264/1080/Big_Buck_Bunny_1080_10s_30MB.mp4?mock_size=2500000000", # 2.5 GB (exceeds 2GB)
            "720p": "https://test-videos.co.uk/vids/bigbuckbunny/mp4/h264/720/Big_Buck_Bunny_720_10s_10MB.mp4?mock_size=2200000000",   # 2.2 GB (exceeds 2GB)
            "480p": "https://test-videos.co.uk/vids/bigbuckbunny/mp4/h264/360/Big_Buck_Bunny_360_10s_5MB.mp4?mock_size=45000000",      # 45 MB (under 50MB, safe)
            "360p": "https://test-videos.co.uk/vids/bigbuckbunny/mp4/h264/360/Big_Buck_Bunny_360_10s_2MB.mp4?mock_size=2000000"        # 2 MB (under 50MB, safe)
        }

    connector = get_connector()
    async with aiohttp.ClientSession(connector=connector) as session:
        try:
            html = await get_html(play_url, session)
            soup = BeautifulSoup(html, "html.parser")
            
            # Find the primary streaming iframe (usually Vidstreaming / GogoPlay)
            iframe = soup.select_one("div.play-video iframe") or soup.select_one("div.anime_video_body_watch_iframe iframe")
            if not iframe:
                raise ScraperError("Failed to locate player iframe on watch page")
                
            player_url = iframe.get("src", "")
            if player_url.startswith("//"):
                player_url = "https:" + player_url
                
            # Direct download page is usually the player domain with /download instead of /streaming.php
            download_page_url = player_url.replace("/streaming.php", "/download")
            
            # Fetch download page HTML
            dl_html = await get_html(download_page_url, session)
            dl_soup = BeautifulSoup(dl_html, "html.parser")
            
            # Find all download links inside class .mirror_link or .dowload
            links = dl_soup.select(".mirror_link .dowload a") or dl_soup.select("div.dowload a")
            
            resolved_links = {}
            for link in links:
                href = link.get("href", "")
                text = link.text.upper()
                
                # Check for standard qualities using regex
                match = re.search(r"(\d{3,4})P", text)
                if match:
                    quality_key = f"{match.group(1)}p"
                    resolved_links[quality_key] = href
                elif "HDP" in text or "ORIGINAL" in text:
                    # Often original quality is marked as Original or HDP (usually 1080p or 720p)
                    resolved_links["1080p"] = href
                    
            # Ensure we filter out dummy javascript links
            resolved_links = {k: v for k, v in resolved_links.items() if v.startswith("http")}
            
            if not resolved_links:
                raise ScraperError("No direct download links parsed from mirror page")
                
            return resolved_links
        except Exception as e:
            print(f"Error scraping download links: {e}")
            return {}
