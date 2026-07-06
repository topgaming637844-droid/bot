import asyncio
import aiohttp
from aiohttp_socks import ProxyConnector

async def test():
    proxy = "socks5://yzjbjptm:mxykfsyptk4x@38.154.203.95:5863"
    connector = ProxyConnector.from_url(proxy)
    try:
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.get("https://graphql.anilist.co", timeout=10) as resp:
                print("Anilist status:", resp.status)
    except Exception as e:
        print("Anilist failed:", e)

    try:
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.get("https://witanime.pics/", timeout=10) as resp:
                print("Witanime status:", resp.status)
    except Exception as e:
        print("Witanime failed:", e)

asyncio.run(test())
