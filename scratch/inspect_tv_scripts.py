from bs4 import BeautifulSoup
from pathlib import Path
import re

html_path = Path("c:/Users/monsm/OneDrive/Desktop/BOT/scratch/witanime_tv.html")
with open(html_path, "r", encoding="utf-8") as f:
    html = f.read()

soup = BeautifulSoup(html, "html.parser")
scripts = soup.find_all("script")
print(f"Total script tags: {len(scripts)}")

out_lines = []
for idx, script in enumerate(scripts):
    content = script.string or script.text or ""
    src = script.get("src", "")
    if src:
        out_lines.append(f"Script {idx+1}: src='{src}'\n")
    else:
        out_lines.append(f"Script {idx+1}: inline, length={len(content)}\n")
        # Check if it defines any arrays or functions
        for line in content.splitlines():
            line_s = line.strip()
            if any(x in line_s for x in ["DivEpisodesList", "Episode", "episode", "ajax", "post", "url"]):
                out_lines.append(f"  {line_s[:150]}\n")

out_file = Path("c:/Users/monsm/OneDrive/Desktop/BOT/scratch/tv_scripts_inspect.txt")
with open(out_file, "w", encoding="utf-8") as f:
    f.writelines(out_lines)
print(f"Saved to {out_file}")
