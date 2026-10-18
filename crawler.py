from playwright.sync_api import sync_playwright

if __name__=="__main__":
    # example code from lecture
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context() # new profile
        page = context.new_page()
        
        page.on("request", lambda request: print(">>>", request.url))
        page.on("response", lambda response: print("<<<", response.status, response.url))
        
        page.goto('https://www.ru.nl')
        
        page.wait_for_timeout(10000)
        browser.close()