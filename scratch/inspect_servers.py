from bs4 import BeautifulSoup
from pathlib import Path

html_path = Path("c:/Users/monsm/OneDrive/Desktop/BOT/scratch/witanime_episode.html")
with open(html_path, "r", encoding="utf-8") as f:
    html = f.read()

soup = BeautifulSoup(html, "html.parser")
servers = soup.select("#episode-servers li a, .episode-servers a, #watch-servers a")
print(f"Found {len(servers)} servers")

for idx, s in enumerate(servers):
    print(f"\nServer {idx+1} full tag:")
    print(s)
    print("Attributes:")
    for attr, val in s.attrs.items():
        print(f"  {attr}: {val}")
    print("Text (raw):", repr(s.text))
