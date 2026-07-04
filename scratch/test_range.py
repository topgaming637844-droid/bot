import sys
from pathlib import Path
project_root = Path("c:/Users/monsm/OneDrive/Desktop/BOT")
sys.path.append(str(project_root))

import asyncio
import aiohttp
from app.utils.user_agents import get_random_user_agent

async def main():
    url = "https://a3.mp4upload.com:183/d/xsx77cwkz3b4quuol2xr2y2ilov55kfhnj5rh5vuuefuzjt5gv4y7w44v7cdb4d5byd5ddoi/video.mp4"
    headers = {
        "User-Agent": get_random_user_agent(),
        "Referer": "https://www.mp4upload.com/",
        "Range": "bytes=0-1023"
    }
    print(f"Testing Range Request: {url}")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, ssl=False, timeout=10) as resp:
                print(f"Status: {resp.status}")
                print(f"Headers: {dict(resp.headers)}")
                data = await resp.read()
                print(f"Data length returned: {len(data)}")
                if resp.status == 206:
                    print("Yes! Senders support HTTP Range requests (206 Partial Content).")
                else:
                    print("No, HTTP Range requests not supported (did not return 206).")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
