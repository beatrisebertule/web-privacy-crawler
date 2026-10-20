from playwright.sync_api import sync_playwright
from tld import get_fld

FIRST_PARTY_URL = "https://www.ru.nl"    
FIRST_PARTY_DOMAIN = get_fld(FIRST_PARTY_URL)

def block_assets(route):
    request = route.request
    req_domain = get_fld(request.url)
    if req_domain != FIRST_PARTY_DOMAIN:
        print(f"BLOCKING {request.url}!")
        route.abort()
    else:
        route.continue_()

if __name__=="__main__":
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(record_har_path = "har/runl.har") 
        page = context.new_page()
        
        page.route("**/*", block_assets)
        page.goto('https://www.ru.nl')
        page.get_by_role("button", name = "Alle cookies toestaan").click()
        # page.screenshot(path="assets/ru-headfull.png")

        page.wait_for_timeout(10000)
        browser.close()