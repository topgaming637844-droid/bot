with open("scratch/naruto_page.html", "r", encoding="utf-8") as f:
    content = f.read()

from bs4 import BeautifulSoup
soup = BeautifulSoup(content, "html.parser")

el_search = soup.select_one(".search-for-episode")
if el_search:
    print("=== .search-for-episode ===")
    print(el_search.prettify().encode('ascii', errors='ignore').decode('ascii')[:1000])

el_list = soup.select_one(".episodes-list-content")
if el_list:
    print("\n=== .episodes-list-content ===")
    print(el_list.prettify().encode('ascii', errors='ignore').decode('ascii')[:1000])
