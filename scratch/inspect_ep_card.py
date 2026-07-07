from bs4 import BeautifulSoup

def main():
    with open("scratch/witanime_home.html", "r", encoding="utf-8") as f:
        html_text = f.read()
        
    soup = BeautifulSoup(html_text, "html.parser")
    ep_card = soup.select_one(".episodes-card-container")
    
    if ep_card:
        with open("scratch/ep_card_html.txt", "w", encoding="utf-8") as f:
            f.write(ep_card.prettify())
        print("Saved ep_card inner HTML to scratch/ep_card_html.txt")
    else:
        print("No ep_card found!")

if __name__ == "__main__":
    main()
