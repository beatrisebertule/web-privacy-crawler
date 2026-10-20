from playwright.sync_api import sync_playwright


if __name__=="__main__":
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context() # new profile
        page = context.new_page()
    
        page.goto('https://www.ru.nl')
        
        # page.screenshot(path="assets/ru-headfull.png")

        page.wait_for_timeout(10000)
        browser.close()