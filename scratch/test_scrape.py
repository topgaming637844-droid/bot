import asyncio
import aiohttp
from app.utils.user_agents import USER_AGENTS

async def test_ua(ua, name):
    url = "https://witanime.life/?search_param=animes&s=Tokyo%20Ghoul"
    # Header from scraper.py
    headers = {
        "User-Agent": ua,
        "Referer": "https://witanime.life/",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Language": "ar,en-US;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "cross-site",
        "Sec-Fetch-User": "?1",
    }
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, headers=headers, ssl=False, timeout=10) as resp:
                print(f"[{name}] {resp.status}")
        except Exception as e:
            print(f"[{name}] Error: {e}")

async def main():
    for i, ua in enumerate(USER_AGENTS):
        await test_ua(ua, f"UA {i}")

if __name__ == "__main__":
    asyncio.run(main())
