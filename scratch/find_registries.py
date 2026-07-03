from bs4 import BeautifulSoup
from pathlib import Path
import re
import json

html_path = Path("c:/Users/monsm/OneDrive/Desktop/BOT/scratch/witanime_episode.html")
with open(html_path, "r", encoding="utf-8") as f:
    html = f.read()

soup = BeautifulSoup(html, "html.parser")
scripts = soup.find_all("script")
print(f"Total scripts: {len(scripts)}")

for idx, script in enumerate(scripts):
    content = script.string or script.text or ""
    if "resourceRegistry" in content or "configRegistry" in content:
        print(f"\nFOUND registries in Script {idx+1}!")
        lines = content.splitlines()
        for line in lines:
            line_s = line.strip()
            if "resourceRegistry" in line_s or "configRegistry" in line_s:
                print("  ", line_s[:150])
