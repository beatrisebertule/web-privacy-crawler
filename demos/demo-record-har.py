from playwright.sync_api import sync_playwright
from time import sleep

if __name__=="__main__":
    with sync_playwright() as p:
        
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            record_har_path = 'etos.nl.har'
        )
        
        page = context.new_page()
        page.goto('https://www.etos.nl')
        
        page.wait_for_timeout(5000)
        
        context.close()
        browser.close()