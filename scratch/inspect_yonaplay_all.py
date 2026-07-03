from bs4 import BeautifulSoup
from pathlib import Path
import base64
import re

html_path = Path("c:/Users/monsm/OneDrive/Desktop/BOT/scratch/yonaplay.html")
with open(html_path, "r", encoding="utf-8") as f:
    html = f.read()

soup = BeautifulSoup(html, "html.parser")

# Find all onclick attributes containing base64 strings
onclicks = re.findall(r"onclick=\"[^\"]+\('[A-Za-z0-9+/=]+'\)\"", html)
print(f"Found {len(onclicks)} onclick matches:")

# Also look for any li, a, button tags
elements = soup.find_all(lambda tag: tag.has_attr("onclick"))
print(f"Found {len(elements)} tags with onclick:")

for idx, el in enumerate(elements):
    oc = el.get("onclick")
    match = re.search(r"['\"]([A-Za-z0-9+/=]{10,})['\"]", oc)
    if match:
        b64_str = match.group(1)
        try:
            decoded = base64.b64decode(b64_str).decode("utf-8")
            el_text = el.text.strip().encode('ascii', 'ignore').decode()
            print(f"  Element {idx+1} ({el.name}): text='{el_text}' | decoded='{decoded}'")
        except Exception as e:
            print(f"  Element {idx+1} ({el.name}): failed to decode {b64_str}: {e}")
            
# Print the JS code that handles players
scripts = soup.find_all("script")
for idx, script in enumerate(scripts):
    content = script.string or script.text or ""
    if "go_to_player" in content or "player" in content:
        print(f"\nScript {idx+1} content:")
        print(content)
