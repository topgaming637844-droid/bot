from pathlib import Path

html_path = Path("c:/Users/monsm/OneDrive/Desktop/BOT/scratch/hglink.html")
with open(html_path, "r", encoding="utf-8") as f:
    html = f.read()

print("Full HTML of hglink.html:")
print(html)
