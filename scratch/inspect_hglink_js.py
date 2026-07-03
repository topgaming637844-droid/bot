from pathlib import Path
import re

js_path = Path("c:/Users/monsm/OneDrive/Desktop/BOT/scratch/hglink_main.js")
with open(js_path, "r", encoding="utf-8") as f:
    js = f.read()

print(f"Length of hglink_main.js: {len(js)} characters")

# Find occurrences of common network terms
for term in ["fetch", "XMLHttpRequest", "ajax", "POST", "GET", "/api/", "/ajax/", "http"]:
    matches = [m.start() for m in re.finditer(term, js, re.IGNORECASE)]
    print(f"Term '{term}': {len(matches)} occurrences")
    
# Let's search for base64 decode (atob) or decryption functions
matches_atob = [m.start() for m in re.finditer(r"atob", js)]
print(f"atob occurrences: {len(matches_atob)}")
