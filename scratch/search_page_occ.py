with open("scratch/naruto_page.html", "r", encoding="utf-8") as f:
    content = f.read()

import re
matches = re.findall(r".{0,40}(?:page|pagin).{0,60}", content, re.IGNORECASE)
print(f"Total occurrences of page/pagin: {len(matches)}")
# Print the first 30 matches (cleaned of non-ascii)
for m in matches[:30]:
    print(m.encode('ascii', errors='ignore').decode('ascii').strip())
