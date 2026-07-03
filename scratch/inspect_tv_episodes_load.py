from bs4 import BeautifulSoup
from pathlib import Path

html_path = Path("c:/Users/monsm/OneDrive/Desktop/BOT/scratch/witanime_tv.html")
with open(html_path, "r", encoding="utf-8") as f:
    html = f.read()

soup = BeautifulSoup(html, "html.parser")
out_lines = []

for div in soup.find_all("div", class_=True):
    classes = div.get("class")
    if any("episodes" in c or "episode" in c for c in classes):
        out_lines.append(f"Class: {classes} | ID: {div.get('id')}\n")
        out_lines.append(div.prettify()[:1000] + "\n")
        out_lines.append("-" * 50 + "\n")

out_file = Path("c:/Users/monsm/OneDrive/Desktop/BOT/scratch/tv_episodes_load.txt")
with open(out_file, "w", encoding="utf-8") as f:
    f.writelines(out_lines)
print(f"Saved to {out_file}")
