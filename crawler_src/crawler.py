"""
Group Project
NWI-IMC074 Online Tracking and Privacy

Student Names: Serge Airapetjan, Beatrise Bertule, Nolan Colter, Daan Smeets
Student Numbers: s1038921, s1105119, sXXXXXXX, sXXXXXXX
"""

import argparse
import csv
import os
import random
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

CRAWL_MODES = ["desktop", "mobile", "block", "ignore"]

# --------------------------------------------------------------------
# Helper Functions
# --------------------------------------------------------------------

def parse_command_line_arguments():
    """Parse and validate the crawler's command line options."""
    argument_parser = argparse.ArgumentParser(
        description="Crawl university homepages for a web privacy measurement."
    )
    argument_parser.add_argument(
        "-m",
        dest="crawl_mode",
        required=True,
        choices=CRAWL_MODES,
        help="Crawl mode: desktop, mobile, block or ignore",
    )
    argument_parser.add_argument(
        "-l",
        dest="site_list_path",
        required=True,
        help="CSV file where each line holds a website domain and its country (e.g. ru.nl,nl)",
    )
    parsed_arguments = argument_parser.parse_args()

    if not os.path.isfile(parsed_arguments.site_list_path):
        argument_parser.error(f"site list file not found: {parsed_arguments.site_list_path}")

    return parsed_arguments


def read_site_list(site_list_path):
    """Return a list of (website_domain, country_code) tuples from the CSV file."""
    sites_to_crawl = []
    with open(site_list_path, newline="", encoding="utf-8") as site_list_file:
        reader = csv.reader(site_list_file)
        next(reader, None) # Skip header row
        for row in reader:
            if len(row) < 2 or not row[0].strip():
                continue  # skip empty or malformed lines
            website_domain = row[0].strip()
            country_code = row[1].strip().lower()
            sites_to_crawl.append((website_domain, country_code))
    return sites_to_crawl

def read_accept_list(accept_list_path):
    accept_list = []
    with open(accept_list_path, "r") as f:
        for row in f:
            accept_list.append(row.strip())
    return accept_list

def accept_cookies(page, accept_list):
    """Accept cookies on the given page if a cookie consent button is available."""
    try:
        # Try to click the button that contains the text "Accept" in any language from the file accept_list.txt
        for accept in accept_list:
            if page.query_selector(f'button:has-text("{accept}")'):
                page.click(f'button:has-text("{accept}")')
                print("Accepted cookies.")
                return
    except Exception as e:
        print("No cookies consent accept button found:", e)

def scroll_down(page):
    """Randomly scroll down to the bottom of the page at random intervals to avoid bot detection."""
    at_bottom = False
    while random.random() > 0.20 and not at_bottom:
        page.mouse.wheel(0, 10 + int(200 * random.random()))
        at_bottom = page.evaluate(
            "() => window.scrollY + window.innerHeight + 100 >= document.documentElement.scrollHeight"
        )
        time.sleep(0.5 + random.random())

def read_crawled_list(crawled_list_path):
    """Read from crawled list txt file the websites that have already been crawled."""
    crawled_list = []
    if not os.path.isfile(crawled_list_path):
        return set()
    with open(crawled_list_path, newline="", encoding="utf-8") as crawled_list_file:
        reader = csv.reader(crawled_list_file)
        for row in reader:
            if len(row) < 2 or not row[0].strip():
                continue  # skip empty or malformed lines
            website_domain = row[0].strip()
            country_code = row[1].strip().lower()
            crawled_list.append((website_domain, country_code))
    return crawled_list

def add_to_crawled_list(crawled_list_path, website_domain, country_code):
    """Add a (website_domain, country_code) tuple to the crawled list txt file."""
    with open(crawled_list_path, "a", newline="", encoding="utf-8") as crawled_list_file:
        writer = csv.writer(crawled_list_file)
        writer.writerow([website_domain, country_code])

# --------------------------------------------------------------------
# Crawlers
# --------------------------------------------------------------------

def crawler_desktop(sites_to_crawl, accept_list):
    """Crawl the list of websites in desktop mode"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            record_har_path="hars/crawler_desktop.har",
            record_har_content="omit",
            record_har_mode="full",
            record_video_dir="videos/"
        )
        remaining_sites_to_crawl = [site for site in sites_to_crawl if site not in read_crawled_list("crawled_list.txt")] # Filter out already crawled sites
        for (website_domain, country_code) in remaining_sites_to_crawl:
            page = context.new_page()
            try:
                print(f"Crawling {website_domain}...")
                page.goto("https://" + website_domain)
                time.sleep(10) # Wait for 10 seconds
                page.screenshot(path=f"screenshots/{website_domain}_before_consent.png", full_page=True)
                accept_cookies(page, accept_list)
                time.sleep(5) # Wait for 5 seconds
                page.screenshot(path=f"screenshots/{website_domain}_after_consent.png", full_page=True)
                scroll_down(page)
                time.sleep(5) # Wait for 5 seconds
            except Exception as e:
                print(f"Error while crawling {website_domain}: {e}")
            finally:
                page.close()
                Path(page.video.path()).rename(f"videos/crawler_desktop_{website_domain}.webm")
                add_to_crawled_list("crawled_list.txt", website_domain, country_code)
                print(f"Finished crawling {website_domain}.")

        context.close()
        browser.close()

def crawler_mobile():
    print("TODO: Implement!")
    return None

def crawler_block():
    print("TODO: Implement!")
    return None

def crawler_ignore():
    print("TODO: Implement!")
    return None


# --------------------------------------------------------------------
# Main
# --------------------------------------------------------------------

if __name__ == "__main__":
    command_line_arguments = parse_command_line_arguments()
    crawl_mode = command_line_arguments.crawl_mode
    sites_to_crawl = read_site_list(command_line_arguments.site_list_path)
    accept_list = read_accept_list("accept_words.txt")

    print(f"Crawl mode: {crawl_mode}")
    print(f"Loaded {len(sites_to_crawl)} websites from {command_line_arguments.site_list_path}")
    # for website_domain, country_code in sites_to_crawl:
    #     print(f"  {website_domain} ({country_code})")

    match crawl_mode:
        case "desktop":
            crawler_desktop(sites_to_crawl, accept_list)
        case "mobile":
            crawler_mobile()
        case "block":
            crawler_block()
        case "ignore":
            crawler_ignore()
        case _:
            print("Wrong crawler mode!")