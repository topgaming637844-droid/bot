from bs4 import BeautifulSoup
from pathlib import Path

html_path = Path("c:/Users/monsm/OneDrive/Desktop/BOT/scratch/witanime_episode.html")
with open(html_path, "r", encoding="utf-8") as f:
    html = f.read()

soup = BeautifulSoup(html, "html.parser")

# Find all script tags
scripts = soup.find_all("script")
print(f"Found {len(scripts)} script tags")

for idx, script in enumerate(scripts):
    content = script.string or script.text or ""
    src = script.get("src", "")
    if src:
        print(f"Script {idx+1}: src='{src}'")
    if "loadIframe" in content or "iframe" in content or "server" in content or "video" in content:
        print(f"Script {idx+1} content sample:")
        lines = content.splitlines()
        for line in lines[:30]:
            print("  ", line.strip())
        print("  ...")
