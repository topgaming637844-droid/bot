import asyncio
import aiohttp
import sys
from pathlib import Path

# Add project root to path
project_root = Path("c:/Users/monsm/OneDrive/Desktop/BOT")
sys.path.append(str(project_root))

from config import config
from app.utils.user_agents import get_random_user_agent
from app.services.anilist import get_connector

async def main():
    url = "https://witanime.pics/wp-content/themes/Anime-Online-Theme/assets/js/gh100.js"
    headers = {"User-Agent": get_random_user_agent()}
    connector = get_connector()
    async with aiohttp.ClientSession(connector=connector) as session:
        async with session.get(url, headers=headers) as response:
            text = await response.text()
            
            lines = text.splitlines()
            output_lines = []
            
            found_indices = [idx for idx, line in enumerate(lines) if "getParameterOffset" in line]
            output_lines.append(f"Found 'getParameterOffset' in {len(found_indices)} lines.\n")
            
            for f_idx in found_indices:
                output_lines.append(f"\nMatch at line {f_idx+1}:\n")
                # Write surrounding 30 lines
                for i in range(max(0, f_idx - 5), min(len(lines), f_idx + 40)):
                    output_lines.append(f"  {i+1}: {lines[i]}\n")
            
            out_file = Path("c:/Users/monsm/OneDrive/Desktop/BOT/scratch/gh100_offset.txt")
            with open(out_file, "w", encoding="utf-8") as f:
                f.writelines(output_lines)
            print(f"Saved match to {out_file}")

if __name__ == "__main__":
    asyncio.run(main())
