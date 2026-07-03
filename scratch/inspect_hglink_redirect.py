from pathlib import Path
import re

js_path = Path("c:/Users/monsm/OneDrive/Desktop/BOT/scratch/hglink_main.js")
with open(js_path, "r", encoding="utf-8") as f:
    js = f.read()

print(f"Length of hglink_main.js: {len(js)}")

# Look for location, window, href, replace, assigning values
for term in ["window", "location", "href", "replace", "assign"]:
    matches = [m.start() for m in re.finditer(term, js, re.IGNORECASE)]
    print(f"Term '{term}': {len(matches)} occurrences")
    for idx, pos in enumerate(matches[:5]):
        start = max(0, pos - 50)
        end = min(len(js), pos + 100)
        print(f"  Match {idx+1}: {js[start:end]}")
