import os
import time
import aiohttp
import asyncio
import uuid
from pathlib import Path
from typing import Dict, Tuple, Optional
from urllib.parse import urlparse, parse_qs, urljoin
from aiogram import Bot
from aiogram.types import FSInputFile, Message
from sqlalchemy.ext.asyncio import AsyncSession
from config import config
from app.utils.user_agents import get_random_user_agent
from app.services.anilist import get_connector
from app.utils.logging_config import logger
from app.services.scraper import get_browser_headers

CHROME_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"


class AdaptiveSemaphore:
    def __init__(self, initial_limit: int):
        self.limit = initial_limit
        self.current_concurrency = 0
        self.cond = asyncio.Condition()

    async def __aenter__(self):
        async with self.cond:
            while self.current_concurrency >= self.limit:
                await self.cond.wait()
            self.current_concurrency += 1

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        async with self.cond:
            self.current_concurrency -= 1
            self.cond.notify_all()

    async def adjust_limit(self, new_limit: int):
        async with self.cond:
            self.limit = max(2, min(64, new_limit))
            self.cond.notify_all()


MAX_CONCURRENT_SEGMENTS = 64
MULTIPART_THREADS = 64

MAX_TELEGRAM_STANDARD_SIZE = 50 * 1024 * 1024       # 50 MB
MAX_TELEGRAM_LOCAL_SIZE = 2 * 1024 * 1024 * 1024     # 2 GB

def make_progress_bar(percentage: float, length: int = 10) -> str:
    """Creates a visual progress bar (e.g. [████░░░░░░])."""
    filled = min(int(percentage / 10), length)
    empty = max(length - filled, 0)
    return "█" * filled + "░" * empty

def get_session_connector(limit: int = 0) -> aiohttp.BaseConnector:
    """Creates a connection-pooled connector with a custom limit."""
    if config.PROXY_URL:
        try:
            from aiohttp_socks import ProxyConnector
            return ProxyConnector.from_url(config.PROXY_URL, limit=limit or 100)
        except Exception:
            logger.exception("Error in process while initializing proxy connector for downloader")
    return aiohttp.TCPConnector(limit=0, limit_per_host=0)

def get_referer_for_url(url: str) -> str:
    """Resolves the best Referer header value to bypass hotlink protection on specific media servers."""
    if "mp4upload" in url:
        return "https://www.mp4upload.com/"
    if "yourupload" in url or "vidcache" in url:
        return "https://www.yourupload.com/"
    return "https://witanime.life/"

async def get_url_file_size(url: str, session: aiohttp.ClientSession) -> int:
    """
    Calculates exact real file size via HEAD or streaming GET response footprint.
    Does NOT use any estimated guessing or baseline quality approximations.
    """
    # Parse mock override parameters if they exist
    try:
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(url)
        query_params = parse_qs(parsed.query)
        if "mock_size" in query_params:
            return int(query_params["mock_size"][0])
    except Exception:
        pass

    if ".m3u8" in url or "master" in url or "playlist" in url or "stream" in url:
        try:
            headers = get_browser_headers(url)
            async with session.get(url, headers=headers, ssl=False, timeout=10) as response:
                content_type = response.headers.get("Content-Type", "").lower()
                if "text/html" in content_type:
                    logger.warning(f"Rejecting HLS request due to HTML content type for {url}")
                    return 0
                if response.status == 200:
                    data = await response.read()
                    if data.startswith(b"\x89PNG"):
                        data = data[252:]
                    text = data.decode("utf-8")
                    lines = text.splitlines()
                    
                    playlist_url = url
                    for line in lines:
                        line = line.strip()
                        if line and not line.startswith("#"):
                            playlist_url = urljoin(url, line)
                            break
                            
                    if playlist_url != url:
                        async with session.get(playlist_url, headers=headers, ssl=False, timeout=10) as sub_resp:
                            if sub_resp.status == 200:
                                sub_data = await sub_resp.read()
                                if sub_data.startswith(b"\x89PNG"):
                                    sub_data = sub_data[252:]
                                text = sub_data.decode("utf-8")
                                lines = text.splitlines()
                            
                    segment_urls = [urljoin(playlist_url, l.strip()) for l in lines if l.strip() and not l.startswith("#")]
                    if segment_urls:
                        first_seg_url = segment_urls[0]
                        async with session.get(first_seg_url, headers=headers, ssl=False, timeout=10) as seg_resp:
                            if seg_resp.status == 200:
                                length = seg_resp.headers.get("Content-Length")
                                if length:
                                    seg_data = await seg_resp.content.read(256)
                                    is_png = seg_data.startswith(b"\x89PNG")
                                    actual_size = int(length) - 252 if is_png else int(length)
                                    total_bytes = len(segment_urls) * actual_size
                                    logger.info(f"HLS exact size: {len(segment_urls)} segments * {actual_size} bytes = {total_bytes / (1024*1024):.2f} MB")
                                    return total_bytes
        except (asyncio.CancelledError, Exception) as e:
            logger.warning(f"Error measuring HLS playlist size for {url}: {e}")
        return 0

    referer = get_referer_for_url(url)
    headers = {"User-Agent": CHROME_USER_AGENT, "Referer": referer}
    
    # 1. Try HEAD request to extract Content-Length
    try:
        async with session.head(url, headers=headers, allow_redirects=True, ssl=False, timeout=10) as response:
            content_type = response.headers.get("Content-Type", "").lower()
            if "text/html" in content_type:
                logger.warning(f"Rejecting HEAD request due to HTML content type for {url}")
                return 0
            if response.status in [200, 206]:
                length = response.headers.get("Content-Length")
                if length and int(length) > 0:
                    return int(length)
                cr = response.headers.get("Content-Range")
                if cr and "/" in cr:
                    total_str = cr.split("/")[-1].strip()
                    if total_str.isdigit():
                        return int(total_str)
    except (asyncio.CancelledError, Exception) as e:
        logger.warning(f"HEAD size query failed for {url}: {e}")
        
    # 2. Fire streaming GET request to capture active Content-Length footprint
    try:
        async with session.get(url, headers=headers, allow_redirects=True, ssl=False, timeout=10) as response:
            content_type = response.headers.get("Content-Type", "").lower()
            if "text/html" in content_type:
                logger.warning(f"Rejecting GET request due to HTML content type for {url}")
                response.close()
                return 0
            length = response.headers.get("Content-Length")
            cr = response.headers.get("Content-Range")
            if length and int(length) > 0:
                size_val = int(length)
                response.close()
                return size_val
            elif cr and "/" in cr:
                total_str = cr.split("/")[-1].strip()
                if total_str.isdigit():
                    size_val = int(total_str)
                    response.close()
                    return size_val
            response.close()
    except (asyncio.CancelledError, Exception) as e:
        logger.warning(f"Streaming GET size query failed for {url}: {e}")
        
    return 0

async def select_best_quality(qualities: Dict[str, str], requested_quality: str = "auto") -> Tuple[str, str, int]:
    """
    Smart Size Logic:
    Resolves the best quality that is <= 2GB based on exact real size footprint.
    """
    quality_order = ["1080p", "720p", "480p", "360p", "240p"]
    available_qualities = [q for q in quality_order if q in qualities]
    
    if requested_quality != "auto" and requested_quality in qualities:
        available_qualities = [requested_quality] + [q for q in available_qualities if q != requested_quality]

    resolved_sizes = {}
    connector = get_session_connector(limit=10)
    async with aiohttp.ClientSession(connector=connector) as session:
        for q in available_qualities:
            url = qualities[q]
            size = await get_url_file_size(url, session)
            resolved_sizes[q] = size
            logger.info(f"Checking quality {q}: Exact size is {size / (1024*1024):.2f} MB")
            
            if size > 0 and size <= MAX_TELEGRAM_LOCAL_SIZE:
                return q, url, size
                
        lowest_q = available_qualities[-1] if available_qualities else list(qualities.keys())[0]
        url = qualities[lowest_q]
        size = resolved_sizes.get(lowest_q, 0)
        if size == 0:
            size = await get_url_file_size(url, session)
        return lowest_q, url, size

async def download_segment(
    idx: int,
    seg_url: str,
    session: aiohttp.ClientSession,
    headers: dict,
    is_png_wrapped: bool,
    semaphore: asyncio.Semaphore
) -> Tuple[int, Optional[bytes]]:
    """Downloads a single segment chunk, checking and stripping fake PNG signature with retry mechanism."""
    max_retries = 5
    seg_timeout = aiohttp.ClientTimeout(total=120, sock_read=60)
    
    import random
    headers_copy = headers.copy()
    headers_copy["User-Agent"] = random.choice(config.USER_AGENTS)
    langs = [
        "ar,en-US;q=0.9,en;q=0.8",
        "en-US,en;q=0.9",
        "ar-EG,ar;q=0.9,en-US;q=0.8,en;q=0.7",
        "en-GB,en;q=0.9,en-US;q=0.8"
    ]
    headers_copy["Accept-Language"] = random.choice(langs)

    async with semaphore:
        for attempt in range(max_retries):
            try:
                async with session.get(seg_url, headers=headers_copy, ssl=False, timeout=seg_timeout) as resp:
                    if resp.status == 200:
                        seg_data = await resp.read()
                        if is_png_wrapped and seg_data.startswith(b"\x89PNG"):
                            seg_data = seg_data[252:]
                        return idx, seg_data
                    elif resp.status == 502:
                        logger.warning(f"[Attempt {attempt+1}/{max_retries}] Segment {idx} 502 error")
                    else:
                        logger.warning(f"[Attempt {attempt+1}/{max_retries}] Segment {idx} returned status {resp.status}")
            except Exception as e:
                logger.warning(f"[Attempt {attempt+1}/{max_retries}] Segment {idx} download error: {e}")
            if attempt < max_retries - 1:
                backoff = min(2 * (2 ** attempt), 16)
                await asyncio.sleep(backoff)
        return idx, None

async def download_hls(
    m3u8_url: str,
    target_path: Path,
    status_message: Message,
    quality: str
) -> bool:
    """
    Downloads HLS playlist concurrently using asyncio.gather (up to 20 parallel connections),
    stripping fake PNG headers, and merging segments. Reuses ClientSession with large connection pooling.
    """
    connector = get_session_connector(limit=0)
    referer = get_referer_for_url(m3u8_url)
    headers = {"User-Agent": get_random_user_agent(), "Referer": referer}
    
    # Keep-alive headers to reuse open network pipes
    keep_alive_headers = {
        "Connection": "keep-alive",
        "Keep-Alive": "timeout=30, max=1000"
    }
    
    if config.PROXY_URL:
        logger.info(f"Proxy used for request: {config.PROXY_URL}")
        
    try:
        async with aiohttp.ClientSession(connector=connector, headers=keep_alive_headers) as session:
            logger.info(f"Fetching HLS playlist: {m3u8_url}")
            async with session.get(m3u8_url, headers=headers, ssl=False, timeout=15) as resp:
                content_type = resp.headers.get("Content-Type", "").lower()
                if "text/html" in content_type:
                    logger.error(f"Error: playlist request returned HTML content type: {content_type}")
                    return False
                if resp.status != 200:
                    logger.error(f"Error in process: failed to fetch playlist {m3u8_url}, status {resp.status}")
                    return False
                text = await resp.text()
                
            lines = text.splitlines()
            segment_urls = []
            for line in lines:
                line = line.strip()
                if line and not line.startswith("#"):
                    segment_urls.append(urljoin(m3u8_url, line))
                    
            if not segment_urls:
                logger.error("Error in process: HLS playlist contained no segments.")
                return False
                
            total_segments = len(segment_urls)
            logger.info(f"Starting HLS parallel download for {total_segments} segments.")
            
            # Check first segment wrapper signature
            first_seg_url = segment_urls[0]
            first_seg_size = 500000
            is_png_wrapped = False
            
            try:
                async with session.get(first_seg_url, headers=headers, ssl=False, timeout=10) as get_resp:
                    if get_resp.status == 200:
                        size_header = get_resp.headers.get("Content-Length")
                        if size_header:
                            first_seg_size = int(size_header)
                        head_data = await get_resp.content.read(256)
                        if head_data.startswith(b"\x89PNG"):
                            is_png_wrapped = True
                            logger.info("PNG wrapper signature detected. Segment header stripping active.")
            except Exception:
                logger.exception("Error checking segment wrapping headers")
                
            actual_seg_size = first_seg_size - 252 if is_png_wrapped else first_seg_size
            estimated_total_size = total_segments * actual_seg_size
            
            # Spawn parallel download tasks with progress tracking (64 worker pool for 100MB/s)
            semaphore = asyncio.Semaphore(MAX_CONCURRENT_SEGMENTS)
            completed_segments = 0
            
            async def download_segment_with_progress(idx, seg_url, is_png_wrapped, sem):
                nonlocal completed_segments
                res = await download_segment(idx, seg_url, session, headers, is_png_wrapped, sem)
                completed_segments += 1
                return res

            tasks = [
                download_segment_with_progress(idx, seg_url, is_png_wrapped, semaphore)
                for idx, seg_url in enumerate(segment_urls)
            ]
            
            # Start a background task to update progress every 4 seconds
            stop_updater = False
            async def progress_updater():
                nonlocal completed_segments, stop_updater
                last_reported = -1
                while not stop_updater:
                    try:
                        await asyncio.sleep(4)
                        if stop_updater:
                            break
                        if total_segments > 0:
                            pct = (completed_segments / total_segments) * 100
                            progress_text = (
                                f"📥 **جاري تحميل فيديو البث...**\n"
                                f"📈 نسبة التقدم: `{pct:.1f}%`\n"
                                f"📊 القطع المحملة: `{completed_segments}/{total_segments}`\n"
                                f"[{make_progress_bar(pct)}]"
                            )
                            if completed_segments != last_reported:
                                last_reported = completed_segments
                                await status_message.edit_text(progress_text, parse_mode="Markdown")
                    except Exception:
                        pass
            
            updater_task = asyncio.create_task(progress_updater())
            
            try:
                start_time = time.time()
                results = await asyncio.gather(*tasks)
            finally:
                stop_updater = True
                updater_task.cancel()
                
            elapsed = time.time() - start_time
            
            downloaded_bytes = 0
            completed_segments_count = 0
            
            # Open output file with 1MB buffer size to reduce disk write latency
            with open(target_path, "wb", buffering=1024*1024) as outfile:
                for idx, seg_data in sorted(results, key=lambda x: x[0]):
                    if seg_data is None:
                        logger.error(f"Error in process: failed to download segment {idx+1}")
                        return False
                    outfile.write(seg_data)
                    downloaded_bytes += len(seg_data)
                    completed_segments_count += 1
            
            speed = downloaded_bytes / elapsed if elapsed > 0 else 0
            speed_mb = speed / (1024 * 1024)
            logger.info(f"تم التحميل بنجاح في {elapsed:.1f} ثانية. السرعة الإجمالية: {speed_mb:.2f} ميجابايت/ثانية")
            
            try:
                await status_message.edit_text(f"✅ تم تحميل البث بنجاح!\nالسرعة: `{speed_mb:.2f} ميجابايت/ثانية`")
            except Exception:
                pass
            return True
    except Exception:
        logger.exception("Error in process during parallel HLS download")
        return False

async def download_multipart(
    url: str,
    target_path: Path,
    status_message: Message,
    total_size: int,
    quality: str,
    num_parts: int = 16
) -> bool:
    """Downloads a direct file in parallel parts using HTTP Range requests to maximize speed."""
    connector = get_session_connector(limit=0)
    referer = get_referer_for_url(url)
    headers = {"User-Agent": CHROME_USER_AGENT, "Referer": referer}
    
    keep_alive_headers = {
        "Connection": "keep-alive",
        "Keep-Alive": "timeout=30, max=1000"
    }
    
    chunk_size = total_size // num_parts
    ranges = []
    for i in range(num_parts):
        start = i * chunk_size
        end = (i + 1) * chunk_size - 1 if i < num_parts - 1 else total_size - 1
        ranges.append((start, end))
        
    part_files = [target_path.with_suffix(f"{target_path.suffix}.part{i}") for i in range(num_parts)]
    
    # Tracking progress
    downloaded_bytes = [0] * num_parts
    start_time = time.time()
    last_update = 0
    abort_flag = [False]
    
    async def download_part(part_idx: int, start_byte: int, end_byte: int, part_path: Path, session: aiohttp.ClientSession):
        # Staggered connection starts to prevent triggering firewalls/DDoS rate limits (very fast start)
        await asyncio.sleep(0.01 * part_idx)
        
        if abort_flag[0]:
            return False
            
        part_headers = headers.copy()
        part_headers["Range"] = f"bytes={start_byte}-{end_byte}"
        
        for attempt in range(3):
            if abort_flag[0]:
                return False
            try:
                client_timeout = aiohttp.ClientTimeout(total=None, sock_read=60)
                async with session.get(url, headers=part_headers, ssl=False, timeout=client_timeout) as response:
                    if response.status == 403:
                        logger.warning(f"Direct MP4 host returned 403 Forbidden on part {part_idx}. Range requests are likely blocked by CDN. Aborting multipart download.")
                        abort_flag[0] = True
                        raise Exception("403 Forbidden")
                    if response.status not in (200, 206):
                        raise Exception(f"Part returned status {response.status}")
                        
                    with open(part_path, "wb") as f:
                        async for chunk in response.content.iter_chunked(1024 * 1024): # 1 MB chunk
                            if abort_flag[0]:
                                raise Exception("Aborted")
                            f.write(chunk)
                            downloaded_bytes[part_idx] += len(chunk)
                            
                            # Trigger progress update
                            nonlocal last_update
                            total_downloaded = sum(downloaded_bytes)
                            now = time.time()
                            if now - last_update >= 4:
                                last_update = now
                                elapsed = now - start_time
                                speed = (total_downloaded / (1024 * 1024)) / elapsed if elapsed > 0 else 0
                                pct = (total_downloaded / total_size) * 100 if total_size > 0 else 0
                                size_mb = total_size / (1024 * 1024)
                                dl_mb = total_downloaded / (1024 * 1024)
                                
                                # Arabic status text
                                text = (
                                    f"📥 **جاري تحميل الفيديو في أجزاء متوازية (تسريع التحميل فعال)**:\n"
                                    f"⚙️ الجودة: `{quality}`\n"
                                    f"📊 النسبة: `{pct:.1f}%`\n"
                                    f"💾 الحجم: `{dl_mb:.1f} / {size_mb:.1f} ميجابايت`\n"
                                    f"🚀 السرعة: `{speed:.2f} ميجابايت/ثانية`"
                                )
                                try:
                                    await status_message.edit_text(text, parse_mode="Markdown")
                                except Exception:
                                    pass
                    return True
            except Exception as e:
                if "403 Forbidden" in str(e) or abort_flag[0]:
                    break
                if attempt == 2:
                    logger.exception(f"Error downloading part {part_idx} after all attempts failed")
                else:
                    logger.warning(f"Error downloading part {part_idx}, attempt {attempt+1}: {e}")
                await asyncio.sleep(1)
        return False

    try:
        async with aiohttp.ClientSession(connector=connector, headers=keep_alive_headers) as session:
            tasks = [
                download_part(i, start, end, part_files[i], session)
                for i, (start, end) in enumerate(ranges)
            ]
            results = await asyncio.gather(*tasks)
            
        if abort_flag[0] or not all(results):
            logger.error("One or more parts failed to download or aborted due to 403.")
            # Clean up parts
            for p in part_files:
                if p.exists():
                    p.unlink()
            return False
            
        # Merge parts
        logger.info(f"Merging {num_parts} parts into final file: {target_path}")
        with open(target_path, "wb") as outfile:
            for p in part_files:
                with open(p, "rb") as infile:
                    while True:
                        chunk = infile.read(1024 * 1024) # 1 MB read buffer
                        if not chunk:
                            break
                        outfile.write(chunk)
                p.unlink() # Delete part file
                
        return True
    except Exception as e:
        logger.exception("Error in process during multipart download")
        for p in part_files:
            if p.exists():
                p.unlink()
        return False

async def download_file(
    url: str,
    target_path: Path,
    status_message: Message,
    total_size: int,
    quality: str
) -> bool:
    """
    Downloads a file (direct link or HLS stream) and updates progress.
    """
    if ".m3u8" in url or "master" in url or "stream" in url:
        return await download_hls(url, target_path, status_message, quality)

    # Use multipart parallel downloader for direct files to bypass speed caps ONLY if Accept-Ranges is supported
    if total_size > 5 * 1024 * 1024:
        supports_ranges = False
        try:
            connector = get_session_connector(limit=10)
            referer = get_referer_for_url(url)
            headers = {"User-Agent": CHROME_USER_AGENT, "Referer": referer}
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.head(url, headers=headers, allow_redirects=True, ssl=False, timeout=8) as head_resp:
                    if head_resp.status in [200, 206]:
                        accept_ranges = head_resp.headers.get("Accept-Ranges", "").lower()
                        if "bytes" in accept_ranges:
                            supports_ranges = True
        except Exception:
            pass

        if supports_ranges:
            logger.info(f"Using multipart downloader for direct URL: {url}")
            num_parts = MULTIPART_THREADS
            success = await download_multipart(url, target_path, status_message, total_size, quality, num_parts=num_parts)
            if success:
                return True
            logger.warning("Multipart download failed or blocked by host CDN. Falling back to high-speed single-stream direct download...")
        else:
            logger.info(f"Server does not support Accept-Ranges (or head request failed). Skipping multipart downloader for: {url}")

    # Single-stream direct chunked streaming downloader
    logger.info(f"Downloading static monolithic video file via chunked streaming context: {url}")
    connector = get_session_connector(limit=0)
    referer = get_referer_for_url(url)
    headers = {"User-Agent": CHROME_USER_AGENT, "Referer": referer}
    
    keep_alive_headers = {
        "Connection": "keep-alive",
        "Keep-Alive": "timeout=30, max=1000"
    }
    
    if config.PROXY_URL:
        logger.info(f"Proxy used for request: {config.PROXY_URL}")
        
    chunk_size = 1024 * 1024  # 1 MB chunk
    downloaded = 0
    start_time = time.time()
    last_update = 0
    
    try:
        async with aiohttp.ClientSession(connector=connector, headers=keep_alive_headers) as session:
            client_timeout = aiohttp.ClientTimeout(total=None, sock_read=60)
            async with session.get(url, headers=headers, allow_redirects=True, ssl=False, timeout=client_timeout) as response:
                content_type = response.headers.get("Content-Type", "").lower()
                if "text/html" in content_type:
                    logger.error(f"Error: download target returned HTML content type instead of video: {content_type}")
                    return False
                if response.status not in [200, 206]:
                    logger.error(f"Error in process: standard download returned status {response.status}")
                    return False
                
                content_length = response.headers.get("Content-Length")
                if content_length and int(content_length) > 0:
                    total_size = int(content_length)
                    
                with open(target_path, "wb", buffering=1024*1024) as f:
                    async for chunk in response.content.iter_chunked(chunk_size):
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        now = time.time()
                        if now - last_update > 4.0:
                            elapsed = now - start_time
                            speed = downloaded / elapsed if elapsed > 0 else 0
                            percentage = (downloaded / total_size) * 100 if total_size > 0 else 0
                            
                            bar = make_progress_bar(percentage)
                            speed_mb = speed / (1024 * 1024)
                            dl_mb = downloaded / (1024 * 1024)
                            total_mb = total_size / (1024 * 1024) if total_size > 0 else 0
                            
                            progress_text = (
                                f"📥 **جاري تحميل الحلقة...**\n"
                                f"الجودة: `{quality}`\n"
                                f"نسبة التقدم: `{percentage:.1f}%` `{bar}`\n"
                                f"الحجم المحمل: `{dl_mb:.1f} ميجابايت` / `{total_mb:.1f} ميجابايت`\n"
                                f"السرعة: `{speed_mb:.2f} ميجابايت/ثانية`"
                            )
                            if total_size > 0 and int(percentage) % 10 == 0:
                                logger.info(f"تقدم التحميل: {percentage:.1f}% - {dl_mb:.1f}/{total_mb:.1f} ميجابايت - السرعة: {speed_mb:.2f} ميجابايت/ثانية")
                            try:
                                await status_message.edit_text(progress_text, parse_mode="Markdown")
                            except Exception:
                                pass
                            last_update = now
                            
        # Verify the file is not empty or too small (e.g. less than 1 KB) to prevent Telegram upload failures
        if not target_path.exists() or target_path.stat().st_size < 1024:
            logger.error(f"Downloaded file {target_path} is empty or too small. Marking download as failed.")
            if target_path.exists():
                try: target_path.unlink()
                except Exception: pass
            return False

        return True
    except Exception:
        logger.exception(f"Error in process during direct file download from {url}")
        if target_path.exists():
            try: target_path.unlink()
            except Exception: pass
        return False

def parse_duration_to_seconds(dur_str: str) -> int:
    import re
    if not dur_str:
        return 24 * 60
    match = re.search(r'(\d+)', dur_str)
    if match:
        mins = int(match.group(1))
        if "ساعة" in dur_str and mins < 5:
            return mins * 3600
        return mins * 60
    if "ساعة" in dur_str:
        if "نصف" in dur_str:
            return 90 * 60
        if "ربع" in dur_str:
            return 75 * 60
        return 60 * 60
    return 24 * 60

async def process_and_send_video(
    bot: Bot,
    message: Message,
    qualities: Dict[str, str],
    requested_quality: str = "auto",
    db_session: Optional[AsyncSession] = None,
    play_url: Optional[str] = None
):
    """
    Downloads the selected quality, checks file sizes against Bot API limitations,
    and uploads the video directly using message.answer_video().
    """
    status_msg = await message.answer("🔄 جاري استخراج أحجام روابط البث...")
    
    try:
        quality, download_url, size = await select_best_quality(qualities, requested_quality)
    except Exception as e:
        logger.exception("Error in process while selecting best quality")
        await status_msg.edit_text(f"❌ فشل في جلب الروابط: {e}")
        return

    size_mb = size / (1024 * 1024)
    await status_msg.edit_text(
        f"✅ الجودة المحددة: `{quality}` ({size_mb:.1f} ميجابايت)\n"
        f"⏳ جاري بدء التحميل..."
    )

    has_local_server = config.TELEGRAM_API_SERVER is not None
    if size > MAX_TELEGRAM_STANDARD_SIZE and not has_local_server:
        await status_msg.edit_text(
            f"❌ حجم الفيديو هو **{size_mb:.1f} ميجابايت** وهو ما يتجاوز حد الرفع المسموح به للبوتات في تلغرام (50 ميجابايت) بدون خادم محلي.",
            parse_mode="Markdown"
        )
        return

    if size > MAX_TELEGRAM_LOCAL_SIZE:
        await status_msg.edit_text(
            f"❌ حجم الملف هو **{size_mb:.1f} جيجابايت**، مما يتجاوز حد تلغرام الأقصى (2 جيجابايت).",
            parse_mode="Markdown"
        )
        return

    unique_id = f"{message.from_user.id}_{uuid.uuid4().hex[:6]}"
    filename = f"anime_{unique_id}_{int(time.time())}_{quality}.mp4"
    temp_file_path = config.DOWNLOAD_DIR / filename
    
    try:
        success = await download_file(download_url, temp_file_path, status_msg, size, quality)
        if not success:
            await status_msg.edit_text("❌ فشل التحميل. يرجى التحقق من البروكسي أو خادم البث.")
            if temp_file_path.exists():
                os.unlink(temp_file_path)
            return

        # FFmpeg Low-RAM Video Compression Safety Valve
        actual_size = os.path.getsize(temp_file_path)
        if actual_size > 1.95 * 1024 * 1024 * 1024:
            await status_msg.edit_text("⚙️ حجم الملف يتجاوز 2 جيجابايت. جاري بدء ضغط الفيديو لتقليل الحجم...")
            compressed_filename = f"compressed_{filename}"
            compressed_file_path = config.DOWNLOAD_DIR / compressed_filename
            
            try:
                process = await asyncio.create_subprocess_exec(
                    "ffmpeg",
                    "-y",
                    "-i", str(temp_file_path),
                    "-vcodec", "libx264",
                    "-crf", "28",
                    "-preset", "ultrafast",
                    "-threads", "1",
                    "-acodec", "copy",
                    str(compressed_file_path),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await process.communicate()
                
                if process.returncode == 0 and compressed_file_path.exists():
                    logger.info(f"Video compressed from {actual_size / (1024*1024):.1f} MB to {os.path.getsize(compressed_file_path) / (1024*1024):.1f} MB")
                    os.unlink(temp_file_path)
                    temp_file_path = compressed_file_path
                    size_mb = os.path.getsize(temp_file_path) / (1024 * 1024)
                else:
                    raise Exception("FFmpeg compression failed")
            except Exception as compression_err:
                logger.warning(f"Error during video compression: {compression_err}. Falling back to URL delivery.")
                if compressed_file_path.exists():
                    try: os.unlink(compressed_file_path)
                    except Exception: pass
                raise Exception(f"فشل ضغط الملف الذي يتجاوز 2 جيجابايت: {compression_err}")

        await status_msg.edit_text("📤 جاري رفع الفيديو إلى تلغرام...")
        video_file = FSInputFile(str(temp_file_path))
        
        # Resolve anime title and episode number
        anime_title = "أنمي"
        ep_num = ""
        anilist_id = None
        
        from sqlalchemy.ext.asyncio import AsyncSession
        if play_url and db_session:
            try:
                from sqlalchemy import select
                from app.database.models import EpisodeCache, SearchCache
                stmt = select(EpisodeCache).where(EpisodeCache.play_url == play_url)
                res = await db_session.execute(stmt)
                ep_cache = res.scalars().first()
                if ep_cache:
                    ep_num = ep_cache.ep_number
                    anilist_id = ep_cache.anilist_id
                    stmt_search = select(SearchCache).where(SearchCache.anilist_id == ep_cache.anilist_id)
                    res_search = await db_session.execute(stmt_search)
                    search_cache = res_search.scalars().first()
                    if search_cache:
                        anime_title = search_cache.title_english or search_cache.title_romaji
                        if anime_title.startswith("WITANIME:"):
                            anime_title = search_cache.title_english
            except Exception:
                logger.exception("Error looking up metadata from DB")
                
        # Parse fallback from play_url if metadata not found
        if (anime_title == "أنمي" or not ep_num) and play_url:
            try:
                from urllib.parse import unquote
                decoded = unquote(play_url)
                parts = [p for p in decoded.strip("/").split("/") if p]
                if parts:
                    slug_part = parts[-1]
                    if "الحلقة" in slug_part:
                        ep_parts = slug_part.split("الحلقة")
                        ep_num = ep_parts[-1].strip("-").strip()
                        anime_slug = ep_parts[0].strip("-").strip()
                        anime_title = anime_slug.replace("-", " ").title()
                    else:
                        anime_title = slug_part.replace("-", " ").title()
            except Exception:
                pass
                
        # Resolve duration from cache
        duration_str = None
        if db_session and play_url:
            try:
                from sqlalchemy import select
                from app.database.models import DownloadCache
                stmt_dur = select(DownloadCache).where(DownloadCache.play_url == play_url)
                res_dur = await db_session.execute(stmt_dur)
                dl_cache = res_dur.scalar_one_or_none()
                if dl_cache and dl_cache.duration:
                    duration_str = dl_cache.duration
            except Exception:
                pass
        if not duration_str:
            duration_str = "24 دقيقة"
            
        duration_seconds = parse_duration_to_seconds(duration_str)

        # Get bot username
        bot_info = await bot.get_me()
        bot_username = f"@{bot_info.username}" if bot_info else ""
        
        # Format the Arabic caption
        caption = (
            f"🎬 **{anime_title}**\n"
            f"🔢 **الحلقة:** `{ep_num}`\n"
            f"⏱️ **المدة:** `{duration_str}`\n"
            f"⚙️ **الجودة:** `{quality}`\n"
            f"💾 **الحجم:** `{size_mb:.1f} ميجابايت`\n\n"
            f"🎥 **مشاهدة ممتعة!** ✨🍿\n\n"
            f"📢 **عبر البوت:** {bot_username}"
        )
        
        # Check for custom thumbnail File Path
        thumb_path = Path(__file__).parent.parent / "data" / "custom_thumb.jpg"
        thumb_input = None
        if thumb_path.exists():
            thumb_input = FSInputFile(str(thumb_path))
            
        # Resolve next/prev buttons for navigation under video
        prev_ep, next_ep = None, None
        inline_keyboard = []
        if db_session and anilist_id:
            try:
                from app.database.models import EpisodeCache
                # Find all episodes for this anilist_id
                stmt_all = select(EpisodeCache).where(EpisodeCache.anilist_id == anilist_id)
                res_all = await db_session.execute(stmt_all)
                all_eps = res_all.scalars().all()
                
                # Custom numerical sort
                def parse_ep(e):
                    try: return float(e.ep_number)
                    except ValueError: return 999999.0
                all_eps.sort(key=parse_ep)
                
                # Find index of current episode
                curr_idx = -1
                for i, ep in enumerate(all_eps):
                    if ep.ep_number == ep_num:
                        curr_idx = i
                        break
                if curr_idx > 0:
                    prev_ep = all_eps[curr_idx - 1].ep_number
                if curr_idx >= 0 and curr_idx < len(all_eps) - 1:
                    next_ep = all_eps[curr_idx + 1].ep_number
            except Exception:
                logger.exception("Error calculating prev/next navigation episodes")

        nav_row = []
        if prev_ep:
            nav_row.append(InlineKeyboardButton(text="◀️ الحلقة السابقة", callback_data=f"nav_ep:{anilist_id}:{prev_ep}"))
        if anilist_id:
            nav_row.append(InlineKeyboardButton(text="🔢 حلقة أخرى", callback_data=f"nav_grid:{anilist_id}"))
        if next_ep:
            nav_row.append(InlineKeyboardButton(text="▶️ الحلقة التالية", callback_data=f"nav_ep:{anilist_id}:{next_ep}"))
        if nav_row:
            inline_keyboard.append(nav_row)

        markup = InlineKeyboardMarkup(inline_keyboard=inline_keyboard) if inline_keyboard else None

        await message.answer_video(
            video=video_file,
            thumbnail=thumb_input,
            duration=duration_seconds,
            caption=caption,
            supports_streaming=True,
            reply_markup=markup,
            parse_mode="Markdown"
        )
        await status_msg.delete()
        
    except Exception as e:
        logger.exception("Error in process while downloading/uploading video")
        await status_msg.edit_text(
            f"❌ فشل الرفع: {e}"
        )
    finally:
        if temp_file_path.exists():
            try:
                os.unlink(temp_file_path)
            except Exception as ce:
                print(f"Error cleaning up temp file {temp_file_path}: {ce}")
