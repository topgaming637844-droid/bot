with open("scratch/naruto_page.html", "r", encoding="utf-8") as f:
    content = f.read()

import re
matches = list(re.finditer(r"/episode/[^\"']*", content))
print(f"Total /episode/ matches: {len(matches)}")
# Print unique episode URLs
urls = sorted(list(set([m.group(0) for m in matches])))
print(f"Total unique episode URLs: {len(urls)}")
for u in urls[:10]:
    print(u)
if len(urls) > 10:
    print("...")
    for u in urls[-10:]:
        print(u)
