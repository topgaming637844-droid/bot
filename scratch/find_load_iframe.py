from bs4 import BeautifulSoup
from pathlib import Path
import re

html_path = Path("c:/Users/monsm/OneDrive/Desktop/BOT/scratch/witanime_episode.html")
with open(html_path, "r", encoding="utf-8") as f:
    html = f.read()

print("Searching for 'loadIframe' in the entire HTML file:")
matches = [m.start() for m in re.finditer(r"loadIframe", html)]
print(f"Found {len(matches)} occurrences")

for idx, pos in enumerate(matches):
    start = max(0, pos - 150)
    end = min(len(html), pos + 150)
    snippet = html[start:end]
    print(f"\nOccurrence {idx+1} near position {pos}:")
    print("-" * 50)
    print(snippet)
    print("-" * 50)
