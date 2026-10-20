from playwright.sync_api import sync_playwright

def handle_req(request):
    if request.resource_type == "script":
        print(request.all_headers())

if __name__=="__main__":
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context() # new profile
        page = context.new_page()
        
        page.on("request", handle_req)
        # page.on("request", lambda request: print(">>>", request.url[:64]))
        # page.on("response", lambda response: print("<<<", response.status, response.url[:64]))
        page.goto('https://www.ru.nl')
        
        page.screenshot(path="assets/ru-headfull.png")

        page.wait_for_timeout(10000)
        browser.close()