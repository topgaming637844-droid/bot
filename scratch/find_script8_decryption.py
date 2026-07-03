from pathlib import Path
import re

js_path = Path("c:/Users/monsm/OneDrive/Desktop/BOT/scratch/script8.js")
with open(js_path, "r", encoding="utf-8") as f:
    js = f.read()

print(f"Length of script8.js: {len(js)}")

# Find all occurrences of processedEpisodeData
matches = [m.start() for m in re.finditer("processedEpisodeData", js)]
print(f"Occurrences of processedEpisodeData: {len(matches)}")

for idx, pos in enumerate(matches):
    start = max(0, pos - 100)
    end = min(len(js), pos + 500)
    print(f"\nMatch {idx+1}:")
    print(js[start:end])
    print("=" * 50)
