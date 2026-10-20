"""
Group Project
NWI-IMC074 Online Tracking and Privacy

Student Names: Serge Airapetjan, Beatrise Bertule, Nolan Colter, Daan Smeets
Student Numbers: sXXXXXXX, s1105119, sXXXXXXX, sXXXXXXX
"""

import argparse
import csv
import os

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
        for row in csv.reader(site_list_file):
            if len(row) < 2 or not row[0].strip():
                continue  # skip empty or malformed lines
            website_domain = row[0].strip()
            country_code = row[1].strip().lower()
            sites_to_crawl.append((website_domain, country_code))
    return sites_to_crawl


# --------------------------------------------------------------------
# Crawlers
# --------------------------------------------------------------------

def crawler_desktop():
    print("TODO: Implement!")
    return None

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

    print(f"Crawl mode: {crawl_mode}")
    print(f"Loaded {len(sites_to_crawl)} websites from {command_line_arguments.site_list_path}")
    # for website_domain, country_code in sites_to_crawl:
    #     print(f"  {website_domain} ({country_code})")

    match crawl_mode:
        case "desktop":
            crawler_desktop()
        case "mobile":
            crawler_mobile()
        case "block":
            crawler_block()
        case "ignore":
            crawler_ignore()
        case _:
            print("Wrong crawler mode!")