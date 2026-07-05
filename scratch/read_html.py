with open("scratch/naruto_page.html", "r", encoding="utf-8") as f:
    content = f.read()
print(f"File length: {len(content)}")
print("First 500 chars:")
print(content[:500].encode('ascii', errors='ignore').decode('ascii'))

import re
matches = re.findall(r"var \w+EpisodeData.*", content)
print(f"Matches for EpisodeData: {len(matches)}")
for m in matches:
    print(m[:100])
