from bs4 import BeautifulSoup
from pathlib import Path

html_path = Path("c:/Users/monsm/OneDrive/Desktop/BOT/scratch/witanime_episode.html")
with open(html_path, "r", encoding="utf-8") as f:
    html = f.read()

soup = BeautifulSoup(html, "html.parser")
scripts = soup.find_all("script")

# Save script 14 content
content = scripts[13].string or scripts[13].text or ""
out_path = Path("c:/Users/monsm/OneDrive/Desktop/BOT/scratch/script14.js")
with open(out_path, "w", encoding="utf-8") as f:
    f.write(content)
print(f"Saved Script 14 to {out_path}")
