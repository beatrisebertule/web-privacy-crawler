from playwright.sync_api import sync_playwright
from time import sleep

if __name__=="__main__":
    with sync_playwright() as p:
        
        iphone_11 = p.devices['iPhone 11 Pro']
        print(f"iphone_11: {iphone_11}")
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            **iphone_11
        )
        
        page = context.new_page()
        page.goto('https://www.ru.nl')
        ua = page.evaluate("navigator.userAgent")
        print(f"UA {ua}")

        sleep(120)
        browser.close()