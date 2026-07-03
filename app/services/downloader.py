import os
import time
import aiohttp
import asyncio
from pathlib import Path
from typing import Dict, Tuple, Optional
from urllib.parse import urlparse, parse_qs, urljoin
from aiogram import Bot
from aiogram.types import FSInputFile, Message
from config import config
from app.utils.user_agents import get_random_user_agent
from app.services.anilist import get_connector
from app.utils.logging_config import logger

MAX_TELEGRAM_STANDARD_SIZE = 50 * 1024 * 1024       # 50 MB
MAX_TELEGRAM_LOCAL_SIZE = 2 * 1024 * 1024 * 1024     # 2 GB

def make_progress_bar(percentage: float, length: int = 10) -> str:
    """Creates a visual progress bar (e.g. [████░░░░░░])."""
    filled = min(int(percentage / 10), length)
    empty = max(length - filled, 0)
    return "█" * filled + "░" * empty

def get_session_connector(limit: int = 50) -> aiohttp.BaseConnector:
    """Creates a connection-pooled connector with a custom limit."""
    if config.PROXY_URL:
        try:
            from aiohttp_socks import ProxyConnector
            return ProxyConnector.from_url(config.PROXY_URL, limit=limit)
        except Exception:
            logger.exception("Error in process while initializing proxy connector for downloader")
    return aiohttp.TCPConnector(limit=limit)

async def get_url_file_size(url: str, session: aiohttp.ClientSession) -> int:
    """
    Validates a stream URL by requesting its headers and retrieving the file size.
    For HLS playlists (.m3u8), estimates the total size by analyzing variant playlists and segment sizes.
    """
    # Parse mock override parameters if they exist
    parsed = urlparse(url)
    query_params = parse_qs(parsed.query)
    if "mock_size" in query_params:
        return int(query_params["mock_size"][0])

    if config.PROXY_URL:
        logger.info(f"Proxy used for request: {config.PROXY_URL}")

    # Estimate HLS stream size
    if ".m3u8" in url or "master" in url or "stream" in url:
        headers = {"User-Agent": get_random_user_agent(), "Referer": "https://witanime.you/"}
        try:
            logger.info(f"Estimating HLS stream size for playlist: {url}")
            async with session.get(url, headers=headers, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    if data.startswith(b"\x89PNG"):
                        data = data[252:]
                    text = data.decode("utf-8")
                    lines = text.splitlines()
                    
                    playlist_url = url
                    if "#EXT-X-STREAM-INF:" in text:
                        for line in lines:
                            line = line.strip()
                            if line and not line.startswith("#"):
                                playlist_url = urljoin(url, line)
                                break
                                
                        if playlist_url != url:
                            async with session.get(playlist_url, headers=headers, timeout=10) as sub_resp:
                                if sub_resp.status == 200:
                                    sub_data = await sub_resp.read()
                                    if sub_data.startswith(b"\x89PNG"):
                                        sub_data = sub_data[252:]
                                    text = sub_data.decode("utf-8")
                                    lines = text.splitlines()
                                
                    segment_urls = [urljoin(playlist_url, l.strip()) for l in lines if l.strip() and not l.startswith("#")]
                    if segment_urls:
                        first_seg_url = segment_urls[0]
                        async with session.get(first_seg_url, headers=headers, timeout=10) as seg_resp:
                            if seg_resp.status == 200:
                                length = seg_resp.headers.get("Content-Length")
                                if length:
                                    seg_data = await seg_resp.read()
                                    is_png = seg_data.startswith(b"\x89PNG")
                                    actual_size = int(length) - 252 if is_png else int(length)
                                    total_est = len(segment_urls) * actual_size
                                    logger.info(f"HLS size estimation: {len(segment_urls)} segments * {actual_size} bytes = {total_est / (1024*1024):.2f} MB")
                                    return total_est
        except Exception:
            logger.exception("Error in process while estimating HLS playlist size")
        return 100 * 1024 * 1024

    headers = {"User-Agent": get_random_user_agent(), "Referer": "https://witanime.you/"}
    try:
        async with session.head(url, headers=headers, allow_redirects=True, timeout=10) as response:
            if response.status == 200:
                length = response.headers.get("Content-Length")
                if length:
                    return int(length)
                    
        async with session.get(url, headers=headers, allow_redirects=True, timeout=10) as response:
            length = response.headers.get("Content-Length")
            if length:
                return int(length)
    except Exception:
        logger.exception(f"Error in process while fetching file size from {url}")
        
    return 0

async def select_best_quality(qualities: Dict[str, str], requested_quality: str = "auto") -> Tuple[str, str, int]:
    """
    Smart Size Logic:
    Resolves the best quality that is <= 2GB.
    """
    quality_order = ["1080p", "720p", "480p", "360p"]
    available_qualities = [q for q in quality_order if q in qualities]
    
    if requested_quality != "auto" and requested_quality in qualities:
        available_qualities = [requested_quality] + [q for q in available_qualities if q != requested_quality]

    connector = get_session_connector(limit=10)
    async with aiohttp.ClientSession(connector=connector) as session:
        for q in available_qualities:
            url = qualities[q]
            size = await get_url_file_size(url, session)
            logger.info(f"Checking quality {q}: Size is {size / (1024*1024):.2f} MB")
            
            if size <= MAX_TELEGRAM_LOCAL_SIZE:
                return q, url, size
                
        lowest_q = available_qualities[-1] if available_qualities else list(qualities.keys())[0]
        url = qualities[lowest_q]
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
    """Downloads a single segment chunk, checking and stripping fake PNG signature."""
    async with semaphore:
        for attempt in range(3):
            try:
                async with session.get(seg_url, headers=headers, timeout=20) as resp:
                    if resp.status == 200:
                        seg_data = await resp.read()
                        if is_png_wrapped and seg_data.startswith(b"\x89PNG"):
                            seg_data = seg_data[252:]
                        return idx, seg_data
            except Exception:
                await asyncio.sleep(0.5)
        return idx, None

async def download_hls(
    m3u8_url: str,
    target_path: Path,
    status_message: Message,
    quality: str
) -> bool:
    """
    Downloads HLS playlist concurrently using asyncio.gather (up to 8 parallel connections),
    stripping fake PNG headers, and merging segments. Reuses ClientSession with large connection pooling.
    """
    connector = get_session_connector(limit=50)
    headers = {"User-Agent": get_random_user_agent(), "Referer": "https://witanime.you/"}
    
    if config.PROXY_URL:
        logger.info(f"Proxy used for request: {config.PROXY_URL}")
        
    try:
        async with aiohttp.ClientSession(connector=connector) as session:
            logger.info(f"Fetching HLS playlist: {m3u8_url}")
            async with session.get(m3u8_url, headers=headers, timeout=15) as resp:
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
                async with session.get(first_seg_url, headers=headers, timeout=10) as get_resp:
                    if get_resp.status == 200:
                        size_header = get_resp.headers.get("Content-Length")
                        if size_header:
                            first_seg_size = int(size_header)
                        head_data = await get_resp.read()
                        if head_data.startswith(b"\x89PNG"):
                            is_png_wrapped = True
                            logger.info("PNG wrapper signature detected. Segment header stripping active.")
            except Exception:
                logger.exception("Error checking segment wrapping headers")
                
            actual_seg_size = first_seg_size - 252 if is_png_wrapped else first_seg_size
            estimated_total_size = total_segments * actual_seg_size
            
            # Spawn parallel download tasks
            semaphore = asyncio.Semaphore(8)
            tasks = [
                download_segment(idx, seg_url, session, headers, is_png_wrapped, semaphore)
                for idx, seg_url in enumerate(segment_urls)
            ]
            
            downloaded_bytes = 0
            start_time = time.time()
            last_update = 0
            
            buffered_data = {}
            next_to_write = 0
            
            # Open output file with 1MB buffer size to reduce disk write latency
            with open(target_path, "wb", buffering=1024*1024) as outfile:
                for future in asyncio.as_completed(tasks):
                    idx, seg_data = await future
                    if seg_data is None:
                        logger.error(f"Error in process: failed to download segment {idx+1}")
                        return False
                        
                    buffered_data[idx] = seg_data
                    downloaded_bytes += len(seg_data)
                    
                    # Write consecutive downloaded segments to disk sequentially
                    while next_to_write in buffered_data:
                        outfile.write(buffered_data[next_to_write])
                        del buffered_data[next_to_write]
                        next_to_write += 1
                        
                    # Throttle progress messages to every 4 seconds to reduce CPU overhead
                    now = time.time()
                    if now - last_update > 4.0 or next_to_write == total_segments:
                        elapsed = now - start_time
                        speed = downloaded_bytes / elapsed if elapsed > 0 else 0
                        percentage = (next_to_write / total_segments) * 100
                        
                        bar = make_progress_bar(percentage)
                        speed_mb = speed / (1024 * 1024)
                        dl_mb = downloaded_bytes / (1024 * 1024)
                        total_mb = estimated_total_size / (1024 * 1024)
                        
                        progress_text = (
                            f"📥 **Downloading HLS stream (Parallel Mode)...**\n"
                            f"Quality: `{quality}`\n"
                            f"Progress: `{percentage:.1f}%` `{bar}` (Segment {next_to_write}/{total_segments})\n"
                            f"Downloaded: `{dl_mb:.1f} MB` / `{total_mb:.1f} MB` (estimated)\n"
                            f"Speed: `{speed_mb:.2f} MB/s`"
                        )
                        
                        # Avoid logging per segment details to minimize CPU/IO logging overhead. Only log every 10%
                        if int(percentage) % 10 == 0:
                            logger.info(f"Download progress: {percentage:.1f}% - {dl_mb:.1f}/{total_mb:.1f} MB - Speed: {speed_mb:.2f} MB/s")
                            
                        try:
                            await status_message.edit_text(progress_text, parse_mode="Markdown")
                        except Exception:
                            pass
                        last_update = now
                        
            logger.info("HLS stream parallel download completed successfully.")
            return True
    except Exception:
        logger.exception("Error in process during parallel HLS download")
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

    connector = get_session_connector(limit=50)
    headers = {"User-Agent": get_random_user_agent(), "Referer": "https://witanime.you/"}
    if config.PROXY_URL:
        logger.info(f"Proxy used for request: {config.PROXY_URL}")
        
    chunk_size = 1024 * 1024  # 1 MB chunk
    downloaded = 0
    start_time = time.time()
    last_update = 0
    
    try:
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.get(url, headers=headers, timeout=120) as response:
                if response.status != 200:
                    logger.error(f"Error in process: standard download returned status {response.status}")
                    return False
                    
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
                                f"📥 **Downloading episode...**\n"
                                f"Quality: `{quality}`\n"
                                f"Progress: `{percentage:.1f}%` `{bar}`\n"
                                f"Downloaded: `{dl_mb:.1f} MB` / `{total_mb:.1f} MB`\n"
                                f"Speed: `{speed_mb:.2f} MB/s`"
                            )
                            if int(percentage) % 10 == 0:
                                logger.info(f"Download progress: {percentage:.1f}% - {dl_mb:.1f}/{total_mb:.1f} MB - Speed: {speed_mb:.2f} MB/s")
                            try:
                                await status_message.edit_text(progress_text, parse_mode="Markdown")
                            except Exception:
                                pass
                            last_update = now
                            
        return True
    except Exception:
        logger.exception(f"Error in process during direct file download from {url}")
        return False

async def process_and_send_video(
    bot: Bot,
    message: Message,
    qualities: Dict[str, str],
    requested_quality: str = "auto"
):
    """
    Downloads the selected quality, checks file sizes against Bot API limitations,
    and uploads the video directly using message.answer_video().
    """
    status_msg = await message.answer("🔄 Resolving streaming link sizes...")
    
    try:
        quality, download_url, size = await select_best_quality(qualities, requested_quality)
    except Exception as e:
        logger.exception("Error in process while selecting best quality")
        await status_msg.edit_text(f"❌ Failed to resolve links: {e}")
        return

    size_mb = size / (1024 * 1024)
    await status_msg.edit_text(
        f"✅ Selected quality: `{quality}` ({size_mb:.1f} MB)\n"
        f"⏳ Initializing download..."
    )

    has_local_server = config.TELEGRAM_API_SERVER is not None
    if size > MAX_TELEGRAM_STANDARD_SIZE and not has_local_server:
        await status_msg.edit_text(
            f"⚠️ **Size warning**:\n"
            f"The video size is **{size_mb:.1f} MB** which exceeds Telegram's standard bot upload limit of **50MB**.\n\n"
            f"Since no local Bot API server is configured, here is your direct link instead:\n"
            f"🔗 [Direct Download Link]({download_url})",
            parse_mode="Markdown"
        )
        return

    if size > MAX_TELEGRAM_LOCAL_SIZE:
        await status_msg.edit_text(
            f"❌ The file size is **{size_mb:.1f} GB**, exceeding Telegram's absolute limit of 2GB.\n"
            f"Please download it directly via your browser:\n"
            f"🔗 [Direct Link]({download_url})",
            parse_mode="Markdown"
        )
        return

    filename = f"anime_{int(time.time())}_{quality}.mp4"
    temp_file_path = config.DOWNLOAD_DIR / filename
    
    try:
        success = await download_file(download_url, temp_file_path, status_msg, size, quality)
        if not success:
            await status_msg.edit_text("❌ Download failed. Check proxy or target host.")
            if temp_file_path.exists():
                os.unlink(temp_file_path)
            return

        await status_msg.edit_text("📤 Uploading video to Telegram...")
        video_file = FSInputFile(str(temp_file_path))
        
        await message.answer_video(
            video=video_file,
            caption=f"🎥 **Enjoy your episode!**\nQuality: `{quality}`\nSize: `{size_mb:.1f} MB`",
            supports_streaming=True,
            parse_mode="Markdown"
        )
        await status_msg.delete()
        
    except Exception as e:
        logger.exception("Error in process while downloading/uploading video")
        await status_msg.edit_text(
            f"❌ Upload failed: {e}\n\n"
            f"Here is your direct link instead:\n"
            f"🔗 [Direct Link]({download_url})"
        )
    finally:
        if temp_file_path.exists():
            try:
                os.unlink(temp_file_path)
            except Exception as ce:
                print(f"Error cleaning up temp file {temp_file_path}: {ce}")
