import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import asyncio
import re
import json
from app.services.scraper import decrypt_episodes

def main():
    with open("scratch/naruto_page.html", "r", encoding="utf-8") as f:
        html = f.read()
        
    processed_match = re.search(r"var processedEpisodeData = '([^']+)';", html)
    if processed_match:
        cipher = processed_match.group(1)
        print(f"processedEpisodeData length: {len(cipher)}")
        try:
            episodes = decrypt_episodes(cipher)
            print(f"Decrypted episodes count from processedEpisodeData: {len(episodes)}")
            if episodes:
                print(f"First ep: {episodes[0]}")
                print(f"Last ep: {episodes[-1]}")
        except Exception as e:
            print(f"Error decrypting: {e}")
    else:
        print("processedEpisodeData not found")

main()
