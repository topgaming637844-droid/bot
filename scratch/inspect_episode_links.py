from bs4 import BeautifulSoup
from pathlib import Path

html_path = Path("c:/Users/monsm/OneDrive/Desktop/BOT/scratch/witanime_episode.html")
with open(html_path, "r", encoding="utf-8") as f:
    html = f.read()

soup = BeautifulSoup(html, "html.parser")
lines = []
for idx, a in enumerate(soup.find_all("a")):
    href = a.get("href", "")
    text = a.text.strip()
    if "anime" in href or "anime" in text or "episode" in href:
        lines.append(f"{idx+1}: href='{href}' | text='{text}'\n")

out_file = Path("c:/Users/monsm/OneDrive/Desktop/BOT/scratch/episode_links.txt")
with open(out_file, "w", encoding="utf-8") as f:
    f.writelines(lines)
print(f"Saved links to {out_file}")
