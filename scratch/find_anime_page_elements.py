from bs4 import BeautifulSoup
from pathlib import Path

html_path = Path("c:/Users/monsm/OneDrive/Desktop/BOT/scratch/witanime_anime.html")
with open(html_path, "r", encoding="utf-8") as f:
    html = f.read()

soup = BeautifulSoup(html, "html.parser")

out_lines = []
out_lines.append(f"Title of anime page: {soup.title.string if soup.title else 'None'}\n\n")

# Print all link tags (href) and text to a file
for idx, a in enumerate(soup.find_all("a")):
    out_lines.append(f"{idx+1}: href='{a.get('href')}' | text='{a.text.strip()}'\n")

# Find divs with class names containing "ep" or "list" or "post"
out_lines.append("\nDiv elements containing certain class names:\n")
for div in soup.find_all("div", class_=True):
    classes = div.get("class")
    if any(any(x in c for x in ["ep", "list", "post", "link", "watch"]) for c in classes):
        out_lines.append(f"  Class: {classes} | ID: {div.get('id')}\n")

out_file = Path("c:/Users/monsm/OneDrive/Desktop/BOT/scratch/witanime_anime_all_links.txt")
with open(out_file, "w", encoding="utf-8") as f:
    f.writelines(out_lines)
print(f"Saved all info to {out_file}")
