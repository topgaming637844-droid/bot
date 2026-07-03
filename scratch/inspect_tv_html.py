from bs4 import BeautifulSoup
from pathlib import Path

html_path = Path("c:/Users/monsm/OneDrive/Desktop/BOT/scratch/witanime_tv.html")
with open(html_path, "r", encoding="utf-8") as f:
    html = f.read()

soup = BeautifulSoup(html, "html.parser")
out_lines = []
out_lines.append(f"Title: {soup.title.string if soup.title else 'None'}\n\n")

# Print all anchor links (href)
for idx, a in enumerate(soup.find_all("a")):
    out_lines.append(f"{idx+1}: href='{a.get('href')}' | text='{a.text.strip()}'\n")
    
out_file = Path("c:/Users/monsm/OneDrive/Desktop/BOT/scratch/witanime_tv_all_links.txt")
with open(out_file, "w", encoding="utf-8") as f:
    f.writelines(out_lines)
print(f"Saved all info to {out_file}")
