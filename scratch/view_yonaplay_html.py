from bs4 import BeautifulSoup
from pathlib import Path
import base64
import re

html_path = Path("c:/Users/monsm/OneDrive/Desktop/BOT/scratch/yonaplay.html")
with open(html_path, "r", encoding="utf-8") as f:
    html = f.read()

soup = BeautifulSoup(html, "html.parser")

print("All li tags:")
for idx, li in enumerate(soup.find_all("li")):
    print(f"  {idx+1}: {li}")
    
print("\nAll script tags:")
for idx, script in enumerate(soup.find_all("script")):
    content = script.string or script.text or ""
    print(f"  Script {idx+1}: src={script.get('src')} | length={len(content)}")
    if content:
        print(content)
