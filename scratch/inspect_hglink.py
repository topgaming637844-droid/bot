from bs4 import BeautifulSoup
from pathlib import Path
import re

html_path = Path("c:/Users/monsm/OneDrive/Desktop/BOT/scratch/hglink.html")
with open(html_path, "r", encoding="utf-8") as f:
    html = f.read()

soup = BeautifulSoup(html, "html.parser")
scripts = soup.find_all("script")
print(f"Found {len(scripts)} scripts")

for idx, script in enumerate(scripts):
    content = script.string or script.text or ""
    src = script.get("src", "")
    if src:
        print(f"Script {idx+1}: src='{src}'")
    else:
        print(f"Script {idx+1} (inline): length={len(content)}")
        # Print lines that look like player config
        for line in content.splitlines():
            line_s = line.strip()
            if any(x in line_s for x in ["file", "source", "url", "stream", "hls", "player", "jwplayer"]):
                print("  ", line_s[:150])
