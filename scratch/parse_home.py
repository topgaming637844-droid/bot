from bs4 import BeautifulSoup

def main():
    with open("scratch/witanime_home.html", "r", encoding="utf-8") as f:
        html_text = f.read()
        
    soup = BeautifulSoup(html_text, "html.parser")
    
    out_lines = []
    
    # Let's inspect class names of top containers
    out_lines.append("--- Selectors on Homepage ---")
    
    ep_cards = soup.select(".episodes-card-container")
    out_lines.append(f"Found .episodes-card-container: {len(ep_cards)}")
    for i, card in enumerate(ep_cards[:10]):
        title_tag = card.select_one(".epcard-title, .anime-card-title, h3, a")
        title = title_tag.text.strip() if title_tag else "No Title"
        link = title_tag.get("href") if (title_tag and title_tag.name == "a") else "None"
        if link == "None" and card.select_one("a"):
            link = card.select_one("a").get("href")
        out_lines.append(f"Ep Card {i+1}: {title} | Link: {link}")
        
    anime_cards = soup.select(".anime-card-container")
    out_lines.append(f"Found .anime-card-container: {len(anime_cards)}")
    for i, card in enumerate(anime_cards[:10]):
        title_tag = card.select_one(".anime-card-title, h3, a")
        title = title_tag.text.strip() if title_tag else "No Title"
        link = card.select_one("a").get("href") if card.select_one("a") else "None"
        out_lines.append(f"Anime Card {i+1}: {title} | Link: {link}")
        
    # Write output to file
    with open("scratch/parsed_home_output.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(out_lines))
    print("Done! Output saved to scratch/parsed_home_output.txt")

if __name__ == "__main__":
    main()
