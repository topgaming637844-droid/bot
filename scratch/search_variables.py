with open("scratch/naruto_page.html", "r", encoding="utf-8") as f:
    content = f.read()

import re
# Find any occurrences of the word encodedEpisode or processedEpisode
matches = re.findall(r".{0,50}(?:encoded|processed)EpisodeData.{0,100}", content)
print(f"Matches count: {len(matches)}")
for m in matches:
    print(m.encode('ascii', errors='ignore').decode('ascii'))
