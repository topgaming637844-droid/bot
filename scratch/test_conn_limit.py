import sys
from pathlib import Path
project_root = Path("c:/Users/monsm/OneDrive/Desktop/BOT")
sys.path.append(str(project_root))

import asyncio
import aiohttp
from app.utils.user_agents import get_random_user_agent

async def test_concurrency(url, num_conns):
    headers = {
        "User-Agent": get_random_user_agent(),
        "Referer": "https://www.mp4upload.com/",
        "Range": "bytes=0-100"
    }
    
    async def request_one(session, idx):
        try:
            async with session.get(url, headers=headers, ssl=False, timeout=10) as resp:
                return idx, resp.status
        except Exception as e:
            return idx, str(e)
            
    print(f"\nTesting {num_conns} parallel connections...")
    async with aiohttp.ClientSession() as session:
        tasks = [request_one(session, i) for i in range(num_conns)]
        results = await asyncio.gather(*tasks)
        
    succeeded = [r for r in results if r[1] == 206]
    failed = [r for r in results if r[1] != 206]
    print(f"Results for {num_conns} connections:")
    print(f"  Succeeded (206): {len(succeeded)}")
    print(f"  Failed/Blocked: {len(failed)}")
    if failed:
        print(f"  Sample failure status: {failed[0][1]}")

async def main():
    url = "https://a3.mp4upload.com:183/d/xsx75s5mz3b4quuo7wrryyixkgo4onpzow6ksitrsez5tnefb67jjxxu7sf4akjkbdfx7mui/video.mp4"
    for limit in [4, 8, 12, 16, 20]:
        await test_concurrency(url, limit)
        await asyncio.sleep(2) # Cooldown

if __name__ == "__main__":
    asyncio.run(main())
