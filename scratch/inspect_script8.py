from bs4 import BeautifulSoup
from pathlib import Path

html_path = Path("c:/Users/monsm/OneDrive/Desktop/BOT/scratch/witanime_tv.html")
with open(html_path, "r", encoding="utf-8") as f:
    html = f.read()

soup = BeautifulSoup(html, "html.parser")
scripts = soup.find_all("script")

# Save script 8 content (which is the inline script that has processedEpisodeData)
content = scripts[7].string or scripts[7].text or ""
out_path = Path("c:/Users/monsm/OneDrive/Desktop/BOT/scratch/script8.js")
with open(out_path, "w", encoding="utf-8") as f:
    f.write(content)
print(f"Saved Script 8 to {out_path}")
