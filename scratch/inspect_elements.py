import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import asyncio
import aiohttp
from bs4 import BeautifulSoup
from app.services.scraper import get_browser_headers

async def main():
    # Set stdout encoding
    sys.stdout.reconfigure(encoding='utf-8')
    
    with open("scratch/naruto_page.html", "r", encoding="utf-8") as f:
        content = f.read()
    
    soup = BeautifulSoup(content, "html.parser")
    
    # Let's find all buttons, select dropdowns, tabs, or lists of episodes
    print("=== Buttons ===")
    for btn in soup.select("button, input[type='button'], .btn, .button"):
        print(f"Tag: {btn.name}, Text: {btn.text.strip().encode('ascii', errors='ignore').decode('ascii')}, Attrs: {btn.attrs}")
        
    print("\n=== Select dropdowns ===")
    for sel in soup.select("select"):
        print(f"Select: {sel.attrs}")
        for opt in sel.select("option"):
            print(f"  Option Text: {opt.text.strip().encode('ascii', errors='ignore').decode('ascii')}, Value: {opt.get('value')}")
            
    print("\n=== Episode lists or containers ===")
    for el in soup.select("[class*='episodes'], [class*='episode'], [id*='episodes'], [id*='episode']"):
        if el.name in ["div", "ul", "ol"]:
            print(f"Tag: {el.name}, Id: {el.get('id')}, Class: {el.get('class')}")
            
    print("\n=== All Script Srcs ===")
    for scr in soup.select("script[src]"):
        print(f"Script Src: {scr.get('src')}")

asyncio.run(main())
