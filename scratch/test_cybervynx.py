import asyncio
import aiohttp
import re
import sys
sys.stdout.reconfigure(encoding='utf-8')

async def main():
    video_id = "t0hyvqpjz7cf"
    
    mirrors = [
        f"https://hlswish.com/e/{video_id}",
        f"https://awish.pro/e/{video_id}",
        f"https://streamwish.to/e/{video_id}",
        f"https://swdyu.com/e/{video_id}",
        f"https://flaswish.com/e/{video_id}",
        f"https://sfastwish.com/e/{video_id}",
        f"https://obeywish.com/e/{video_id}",
        f"https://jodwish.com/e/{video_id}",
        f"https://embedwish.com/e/{video_id}",
        f"https://cdnwish.com/e/{video_id}",
        f"https://strwish.xyz/e/{video_id}",
    ]
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Referer": "https://witanime.pics/",
        "Accept-Encoding": "gzip, deflate",
    }
    
    async with aiohttp.ClientSession() as session:
        for url in mirrors:
            try:
                async with session.get(url, headers=headers, ssl=False, timeout=8) as resp:
                    if resp.status != 200:
                        print(f"  SKIP {url} -> status {resp.status}")
                        continue
                    text = await resp.text()
                    has_packed = bool(re.search(r"eval\(function\(p,a,c,k,e,d\)", text))
                    has_m3u8 = bool(re.findall(r'\.m3u8', text))
                    if has_packed or has_m3u8:
                        print(f"  HIT {url} -> packed={has_packed}, m3u8={has_m3u8}, len={len(text)}")
                    else:
                        print(f"  MISS {url} -> packed={has_packed}, m3u8={has_m3u8}, len={len(text)}")
            except Exception as e:
                print(f"  ERR {url} -> {type(e).__name__}: {e}")

asyncio.run(main())
