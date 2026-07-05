import asyncio
import aiohttp
from urllib.parse import quote

async def test_kitsu(query: str):
    print(f"\nTesting Kitsu API search for: '{query}'")
    url = f"https://kitsu.io/api/edge/anime?filter[text]={quote(query)}&page[limit]=5"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/vnd.api+json",
        "Content-Type": "application/vnd.api+json"
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=10) as resp:
                print(f"  Status: {resp.status}")
                if resp.status == 200:
                    data = await resp.json()
                    media_list = data.get("data", [])
                    print(f"  Found {len(media_list)} results:")
                    for m in media_list:
                        attrs = m.get("attributes", {})
                        canonical_title = attrs.get("canonicalTitle")
                        slug = attrs.get("slug")
                        abbreviated_titles = attrs.get("abbreviatedTitles", [])
                        titles = attrs.get("titles", {})
                        romaji = titles.get("en_jp")
                        english = titles.get("en")
                        print(f"    - Canonical: {canonical_title} | Slug: {slug} | Romaji: {romaji} | Eng: {english} | Abbrev: {abbreviated_titles}")
                else:
                    print(f"  Failed: {resp.status}")
    except Exception as e:
        print(f"  Error: {e}")

async def main():
    await test_kitsu("Demon Slayer")
    await test_kitsu("DemonSlayer")

if __name__ == "__main__":
    asyncio.run(main())
