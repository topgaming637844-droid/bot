import asyncio
import aiohttp

DOMAINS = [
    "witanime.life",
    "witanime.pics",
    "witanime.red",
    "witanime.com",
    "witanime.site",
    "witanime.org",
]

async def test_domain_search(domain):
    urls = [
        f"https://{domain}/?search_param=animes&s=Tokyo%20Ghoul",
        f"https://{domain}/?s=Tokyo%20Ghoul",
        f"https://{domain}/anime/tokyo-ghoul-tv",
    ]
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ar,en-US;q=0.9,en;q=0.8",
    }
    async with aiohttp.ClientSession() as session:
        for url in urls:
            try:
                async with session.get(url, headers=headers, ssl=False, timeout=8) as resp:
                    print(f"[{domain}] GET {url} -> status {resp.status}")
            except Exception as e:
                print(f"[{domain}] GET {url} -> error {e}")

async def main():
    for d in DOMAINS:
        await test_domain_search(d)

if __name__ == "__main__":
    asyncio.run(main())
