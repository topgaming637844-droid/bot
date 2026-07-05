import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import asyncio
import aiohttp
import re
import json
import base64
from app.services.scraper import get_browser_headers, safe_b64decode

async def main():
    # Test Naruto (original)
    url_naruto = "https://witanime.life/anime/naruto/"
    # Test Naruto Shippuden
    url_shippuden = "https://witanime.life/anime/naruto-shippuden/"
    
    headers = get_browser_headers(url_naruto)
    async with aiohttp.ClientSession() as session:
        for name, url in [("Naruto", url_naruto), ("Naruto Shippuden", url_shippuden)]:
            async with session.get(url, headers=headers) as resp:
                print(f"\n=== {name} ({url}) ===")
                print(f"Status: {resp.status}")
                if resp.status != 200:
                    continue
                html = await resp.text()
                
                # Check for encodedEpisodeData
                encoded_match = re.search(r"var encodedEpisodeData = '([^']+)';", html)
                if encoded_match:
                    try:
                        decoded = safe_b64decode(encoded_match.group(1)).decode("utf-8")
                        data = json.loads(decoded)
                        print(f"encodedEpisodeData found! Type: {type(data)}")
                        if isinstance(data, dict):
                            print(f"Keys: {list(data.keys())}")
                            # Print number of episodes
                            for k, v in data.items():
                                print(f"Key '{k}': length {len(v) if isinstance(v, list) else 'not list'}")
                        elif isinstance(data, list):
                            print(f"List length: {len(data)}")
                            if data:
                                print(f"Sample: {data[0]}")
                    except Exception as e:
                        print(f"Error decoding encodedEpisodeData: {e}")
                else:
                    print("encodedEpisodeData NOT found.")
                    
                # Check for processedEpisodeData
                processed_match = re.search(r"var processedEpisodeData = '([^']+)';", html)
                if processed_match:
                    print(f"processedEpisodeData found! Length: {len(processed_match.group(1))}")
                else:
                    print("processedEpisodeData NOT found.")

asyncio.run(main())
