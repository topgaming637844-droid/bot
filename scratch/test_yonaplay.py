import sys
from pathlib import Path
project_root = Path("c:/Users/monsm/OneDrive/Desktop/BOT")
sys.path.append(str(project_root))

import asyncio
import aiohttp
from app.utils.user_agents import get_random_user_agent

async def test_referer(session, url, desc, ref_val):
    headers = {
        "User-Agent": get_random_user_agent(),
    }
    if ref_val:
        headers["Referer"] = ref_val
    try:
        async with session.get(url, headers=headers, ssl=False, timeout=10) as resp:
            print(f"[{desc}] Status: {resp.status}, Content Length: {resp.headers.get('Content-Length')}")
            if resp.status == 200:
                text = await resp.text()
                print(f"[{desc}] Snippet: {text[:500]}")
    except Exception as e:
        print(f"[{desc}] Error: {e}")

async def main():
    url = "https://yonaplay.net/embed.php?id=3009&apiKey=23a97133-caf3-4eb4-9466-93d0a4ff8198"
    
    async with aiohttp.ClientSession() as session:
        await test_referer(session, url, "Exact Episode watch page referer", "https://witanime.pics/episode/boruto-naruto-next-generations-%d8%a7%d9%84%d8%ad%d9%84%d9%82%d8%a9-250/")
        await test_referer(session, url, "No referer", None)
        await test_referer(session, url, "Witanime domain referer", "https://witanime.pics")
        await test_referer(session, url, "Witanime domain with slash", "https://witanime.pics/")

if __name__ == "__main__":
    asyncio.run(main())
