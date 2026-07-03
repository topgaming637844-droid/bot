import os
import time
import aiohttp
import asyncio
from pathlib import Path
from typing import Dict, Tuple, Optional
from urllib.parse import urlparse, parse_qs
from aiogram import Bot
from aiogram.types import FSInputFile, Message
from config import config
from app.utils.user_agents import get_random_user_agent
from app.services.anilist import get_connector

MAX_TELEGRAM_STANDARD_SIZE = 50 * 1024 * 1024       # 50 MB
MAX_TELEGRAM_LOCAL_SIZE = 2 * 1024 * 1024 * 1024     # 2 GB

def make_progress_bar(percentage: float, length: int = 10) -> str:
    """Creates a visual progress bar (e.g. [████░░░░░░])."""
    filled = min(int(percentage / 10), length)
    empty = max(length - filled, 0)
    return "█" * filled + "░" * empty

async def get_url_file_size(url: str, session: aiohttp.ClientSession) -> int:
    """
    Validates a stream URL by requesting its headers and retrieving the file size.
    Performs a HEAD request, falling back to a GET request if HEAD is rejected.
    """
    # Parse mock override parameters if they exist
    parsed = urlparse(url)
    query_params = parse_qs(parsed.query)
    if "mock_size" in query_params:
        return int(query_params["mock_size"][0])

    headers = {"User-Agent": get_random_user_agent()}
    try:
        # Try HEAD request
        async with session.head(url, headers=headers, allow_redirects=True, timeout=10) as response:
            if response.status == 200:
                length = response.headers.get("Content-Length")
                if length:
                    return int(length)
                    
        # Fallback to GET request if HEAD failed to retrieve Content-Length
        async with session.get(url, headers=headers, allow_redirects=True, timeout=10) as response:
            length = response.headers.get("Content-Length")
            if length:
                return int(length)
    except Exception as e:
        print(f"HEAD size check failed for {url}: {e}")
        
    return 0

async def select_best_quality(qualities: Dict[str, str], requested_quality: str = "auto") -> Tuple[str, str, int]:
    """
    Smart Size Logic:
    Resolves the best quality that is <= 2GB.
    Returns: Tuple (selected_quality, url, file_size)
    """
    # Sort qualities from highest to lowest
    quality_order = ["1080p", "720p", "480p", "360p"]
    
    # Filter available qualities matching our order
    available_qualities = [q for q in quality_order if q in qualities]
    
    # If the user requested a specific quality, prioritize it by moving it to the top
    if requested_quality != "auto" and requested_quality in qualities:
        available_qualities = [requested_quality] + [q for q in available_qualities if q != requested_quality]

    connector = get_connector()
    async with aiohttp.ClientSession(connector=connector) as session:
        for q in available_qualities:
            url = qualities[q]
            size = await get_url_file_size(url, session)
            print(f"Checking quality {q}: Size is {size / (1024*1024):.2f} MB")
            
            # If the size is within the Telegram absolute limit (2GB)
            if size <= MAX_TELEGRAM_LOCAL_SIZE:
                return q, url, size
                
        # If no quality is <= 2GB, return the lowest available quality as fallback
        lowest_q = available_qualities[-1] if available_qualities else list(qualities.keys())[0]
        url = qualities[lowest_q]
        size = await get_url_file_size(url, session)
        return lowest_q, url, size

async def download_file(
    url: str,
    target_path: Path,
    status_message: Message,
    total_size: int,
    quality: str
) -> bool:
    """
    Downloads a file in chunks and updates progress inside a Telegram message.
    """
    connector = get_connector()
    headers = {"User-Agent": get_random_user_agent()}
    
    chunk_size = 1024 * 1024  # 1 MB chunk
    downloaded = 0
    start_time = time.time()
    last_update = 0
    
    try:
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.get(url, headers=headers, timeout=120) as response:
                if response.status != 200:
                    return False
                    
                with open(target_path, "wb") as f:
                    async for chunk in response.content.iter_chunked(chunk_size):
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        # Throttle updates to Telegram to avoid rate limit (once every 3 seconds)
                        now = time.time()
                        if now - last_update > 3.0:
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
                            try:
                                await status_message.edit_text(progress_text, parse_mode="Markdown")
                            except Exception:
                                pass  # Ignore minor telegram errors
                            last_update = now
                            
        return True
    except Exception as e:
        print(f"Error during file download: {e}")
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
    
    # 1. Run Smart Size Logic to find the best quality link
    try:
        quality, download_url, size = await select_best_quality(qualities, requested_quality)
    except Exception as e:
        await status_msg.edit_text(f"❌ Failed to resolve links: {e}")
        return

    size_mb = size / (1024 * 1024)
    await status_msg.edit_text(
        f"✅ Selected quality: `{quality}` ({size_mb:.1f} MB)\n"
        f"⏳ Initializing download..."
    )

    # 2. Check if the file exceeds standard Telegram Bot upload limit (50MB) 
    # without a local Bot API server configuration
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

    # If the file exceeds 2GB (Telegram absolute cap)
    if size > MAX_TELEGRAM_LOCAL_SIZE:
        await status_msg.edit_text(
            f"❌ The file size is **{size_mb:.1f} GB**, exceeding Telegram's absolute limit of 2GB.\n"
            f"Please download it directly via your browser:\n"
            f"🔗 [Direct Link]({download_url})",
            parse_mode="Markdown"
        )
        return

    # 3. Download the file locally
    filename = f"anime_{int(time.time())}_{quality}.mp4"
    temp_file_path = config.DOWNLOAD_DIR / filename
    
    try:
        success = await download_file(download_url, temp_file_path, status_msg, size, quality)
        if not success:
            await status_msg.edit_text("❌ Download failed. Check proxy or target host.")
            if temp_file_path.exists():
                os.unlink(temp_file_path)
            return

        # 4. Upload and send the video file natively
        await status_msg.edit_text("📤 Uploading video to Telegram...")
        video_file = FSInputFile(str(temp_file_path))
        
        # Native answer_video so it plays directly inside Telegram
        await message.answer_video(
            video=video_file,
            caption=f"🎥 **Enjoy your episode!**\nQuality: `{quality}`\nSize: `{size_mb:.1f} MB`",
            supports_streaming=True,
            parse_mode="Markdown"
        )
        await status_msg.delete()
        
    except Exception as e:
        await status_msg.edit_text(
            f"❌ Upload failed: {e}\n\n"
            f"Here is your direct link instead:\n"
            f"🔗 [Direct Link]({download_url})"
        )
    finally:
        # Always clean up downloaded files
        if temp_file_path.exists():
            try:
                os.unlink(temp_file_path)
            except Exception as ce:
                print(f"Error cleaning up temp file {temp_file_path}: {ce}")
