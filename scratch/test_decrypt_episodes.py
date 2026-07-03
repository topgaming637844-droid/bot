import base64
import json
import re
from pathlib import Path

def decrypt_episodes(processed_episode_data):
    parts = processed_episode_data.split('.')
    data_bytes = base64.b64decode(parts[0])
    key_bytes = base64.b64decode(parts[1])
    
    decrypted_chars = []
    for i in range(len(data_bytes)):
        decrypted_chars.append(chr(data_bytes[i] ^ key_bytes[i % len(key_bytes)]))
        
    decrypted_str = "".join(decrypted_chars)
    return json.loads(decrypted_str)

def main():
    html_path = Path("c:/Users/monsm/OneDrive/Desktop/BOT/scratch/witanime_tv.html")
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()
        
    # Extract processedEpisodeData
    match = re.search(r"var processedEpisodeData = '([^']+)';", html)
    if not match:
        print("Could not find processedEpisodeData in HTML")
        return
        
    data_str = match.group(1)
    episodes = decrypt_episodes(data_str)
    
    print(f"Decrypted {len(episodes)} episodes!")
    print("\nFirst 5 episodes:")
    for ep in episodes[:5]:
        print(f"  Number: {ep.get('number')} | Type: {ep.get('type')} | URL: {ep.get('url')}")
        
    print("\nLast 5 episodes:")
    for ep in episodes[-5:]:
        print(f"  Number: {ep.get('number')} | Type: {ep.get('type')} | URL: {ep.get('url')}")

if __name__ == "__main__":
    main()
