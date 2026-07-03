import asyncio
import aiohttp
import sys
import re
from pathlib import Path

# Add project root to path
project_root = Path("c:/Users/monsm/OneDrive/Desktop/BOT")
sys.path.append(str(project_root))

from config import config
from app.utils.user_agents import get_random_user_agent
from app.services.anilist import get_connector

def unpack_dean_edwards(packed_text):
    # Search for the arguments inside the eval(function(p,a,c,k,e,d)...)
    # The structure is: eval(function(p,a,c,k,e,d){...}('p_content', a, c, 'k_content'.split('|'), ...))
    pattern = r"\}\s*\(\s*(['\"].*?['\"])\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(['\"].*?['\"])\s*\.split\(['\"]\|['\"]\)\)"
    match = re.search(pattern, packed_text, re.DOTALL)
    if not match:
        print("Could not parse packer parameters")
        return ""
        
    p_raw, a_str, c_str, k_raw = match.groups()
    a = int(a_str)
    c = int(c_str)
    
    # Strip quotes
    p = p_raw[1:-1]
    # Replace escaped quotes inside p
    p = re.sub(r'\\(["\'])', r'\1', p)
    
    # Extract tokens from k
    k_content = k_raw[1:-1]
    k = k_content.split("|")
    
    def base36encode(number):
        # We don't need this, we only need decode
        pass
        
    def replace_word(word_match):
        word = word_match.group(0)
        try:
            # Parse word in base a
            val = 0
            for char in word:
                if char.isdigit():
                    digit = int(char)
                else:
                    digit = ord(char.lower()) - ord('a') + 10
                if digit >= a:
                    return word
                val = val * a + digit
            if val < len(k) and k[val]:
                return k[val]
        except Exception:
            pass
        return word

    unpacked = re.sub(r"\b\w+\b", replace_word, p)
    return unpacked.replace("\\'", "'")

async def main():
    url = "https://hanerix.com/e/5rzzsm2fl9b9"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://witanime.you/"
    }
    connector = get_connector()
    async with aiohttp.ClientSession(connector=connector) as session:
        try:
            print(f"Requesting {url}...")
            async with session.get(url, headers=headers) as response:
                text = await response.text()
                
            # Extract eval(...) script
            script_match = re.search(r"eval\(function\(p,a,c,k,e,d\).*?\.split\(['\"]\|['\"]\)\)\)", text, re.DOTALL)
            if not script_match:
                print("No eval function found!")
                return
                
            packed = script_match.group(0)
            print("Unpacking JS...")
            unpacked = unpack_dean_edwards(packed)
            
            # Find master.m3u8 or txt URLs
            m3u8_links = re.findall(r'https?://[^\s"\']+\.m3u8[^\s"\']*', unpacked)
            print(f"Found {len(m3u8_links)} m3u8 links in unpacked JS:")
            for link in m3u8_links:
                print("  ", link)
                
            txt_links = re.findall(r'https?://[^\s"\']+\.txt[^\s"\']*', unpacked)
            print(f"Found {len(txt_links)} txt links in unpacked JS:")
            for link in txt_links:
                print("  ", link)
                
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
