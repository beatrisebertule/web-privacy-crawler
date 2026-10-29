"""
Group Project
NWI-IMC074 Online Tracking and Privacy

Student Names: Serge Airapetjan, Beatrise Bertule, Nolan Colter, Daan Smeets
Student Numbers: s1038921, s1105119, s1167654, sXXXXXXX

Usage:
    python crawler_src/crawler.py -m desktop -l sites.csv
    python crawler_src/crawler.py -m mobile -l sites.csv
    python crawler_src/crawler.py -m block -l sites.csv
    python crawler_src/crawler.py -m ignore -l sites.csv
"""

# Standard library imports
import argparse
import csv
import enum
import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

# Third party imports
from playwright.sync_api import Browser, Page, Playwright, sync_playwright


# *******************************************
# Constants
# *******************************************

# Paths resolve against the repo root, so the crawler runs the same from any working directory.
REPO_ROOT = Path(__file__).resolve().parent.parent
ACCEPT_WORDS_PATH = REPO_ROOT / "accept_words.txt"

MOBILE_DEVICE_NAME = "Pixel 10"


class CrawlMode(enum.Enum):
    """
    The four crawl configurations from the assignment.

    Desktop, mobile and block accept the consent dialog. Ignore never touches it.
    """

    DESKTOP = "desktop"
    MOBILE = "mobile"
    BLOCK = "block"
    IGNORE = "ignore"

    @property
    def accepts_consent(self) -> bool:
        return self is not CrawlMode.IGNORE

    @property
    def output_directory(self) -> Path:
        return REPO_ROOT / f"crawl_data_{self.value}"

    @property
    def crawled_list_path(self) -> Path:
        # One resume file per mode, so finishing the desktop crawl doesn't skip the mobile one.
        return REPO_ROOT / f"crawled_{self.value}.txt"


@dataclass(frozen=True)
class WaitSchedule:
    """
    Seconds to sleep between crawl steps.

    Defaults are the assignment's schedule:
    page load -> 10 s -> accept -> 5 s -> scroll -> 5 s -> close.
    Tests pass zeros so a visit to a local fixture page takes a second.
    """

    after_page_load: float = 10.0
    after_consent: float = 5.0
    after_scroll: float = 5.0


@dataclass
class VisitResult:
    """What one visit produced, for the caller's log and for tests."""

    site_name: str
    final_url: str | None = None
    consent_clicked: bool = False
    error: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.error is None


# *******************************************
# Input files
# *******************************************

def parse_command_line_arguments() -> argparse.Namespace:
    """Parse and validate the crawler's command line options."""
    argument_parser = argparse.ArgumentParser(
        description="Crawl university homepages for a web privacy measurement."
    )
    argument_parser.add_argument(
        "-m",
        dest="crawl_mode",
        required=True,
        type=CrawlMode,
        choices=list(CrawlMode),
        metavar="{" + ",".join(mode.value for mode in CrawlMode) + "}",
        help="Crawl mode: desktop, mobile, block or ignore",
    )
    argument_parser.add_argument(
        "-l",
        dest="site_list_path",
        required=True,
        type=Path,
        help="CSV file where each line holds a website domain and its country (e.g. ru.nl,nl)",
    )
    parsed_arguments = argument_parser.parse_args()

    if not parsed_arguments.site_list_path.is_file():
        argument_parser.error(f"site list file not found: {parsed_arguments.site_list_path}")

    return parsed_arguments


def read_site_list(site_list_path: Path) -> list[tuple[str, str]]:
    """
    Return (website_domain, country_code) tuples from the site CSV.

    First row is a header and is skipped. Empty and malformed rows are skipped too.
    """
    sites_to_crawl = []
    with open(site_list_path, newline="", encoding="utf-8") as site_list_file:
        site_rows = csv.reader(site_list_file)
        next(site_rows, None)
        for row in site_rows:
            if len(row) < 2 or not row[0].strip():
                continue
            website_domain = row[0].strip()
            country_code = row[1].strip().lower()
            sites_to_crawl.append((website_domain, country_code))
    return sites_to_crawl


def read_accept_words(accept_words_path: Path) -> list[str]:
    """Return the consent button phrases, one per line, in file order."""
    with open(accept_words_path, encoding="utf-8") as accept_words_file:
        return [line.strip() for line in accept_words_file if line.strip()]


# *******************************************
# Resume list
# *******************************************

def read_crawled_list(crawled_list_path: Path) -> set[tuple[str, str]]:
    """Return the (website_domain, country_code) pairs already finished in this mode."""
    if not crawled_list_path.is_file():
        return set()
    crawled_sites = set()
    with open(crawled_list_path, newline="", encoding="utf-8") as crawled_list_file:
        for row in csv.reader(crawled_list_file):
            if len(row) < 2 or not row[0].strip():
                continue
            crawled_sites.add((row[0].strip(), row[1].strip().lower()))
    return crawled_sites


def add_to_crawled_list(crawled_list_path: Path, website_domain: str, country_code: str) -> None:
    """Append one finished site to the resume list."""
    with open(crawled_list_path, "a", newline="", encoding="utf-8") as crawled_list_file:
        csv.writer(crawled_list_file).writerow([website_domain, country_code])


def select_sites_to_crawl(
    sites: list[tuple[str, str]],
    crawled_list_path: Path,
) -> list[tuple[str, str]]:
    """Return the sites not yet in the resume list, in site list order."""
    already_crawled = read_crawled_list(crawled_list_path)
    return [site for site in sites if site not in already_crawled]


# *******************************************
# Page interaction
# *******************************************

def accept_cookies(page: Page, accept_words: list[str]) -> bool:
    """
    Click the first button whose text contains one of the accept phrases.

    Phrases are tried in file order. Returns whether anything was clicked.
    """
    try:
        for accept_phrase in accept_words:
            button_selector = f'button:has-text("{accept_phrase}")'
            if page.query_selector(button_selector):
                page.click(button_selector)
                print("Accepted cookies.")
                return True
    except Exception as click_error:
        print("No cookies consent accept button found:", click_error)
    return False


def scroll_down(page: Page) -> None:
    """Scroll down the page in random steps at random intervals, to look less like a bot."""
    at_bottom = False
    while random.random() > 0.20 and not at_bottom:
        page.mouse.wheel(0, 10 + int(200 * random.random()))
        at_bottom = page.evaluate(
            "() => window.scrollY + window.innerHeight + 100 >= document.documentElement.scrollHeight"
        )
        time.sleep(0.5 + random.random())


# *******************************************
# One visit
# *******************************************

def build_context_options(
    playwright: Playwright,
    crawl_mode: CrawlMode,
    output_directory: Path,
    site_name: str,
) -> dict:
    """Playwright context options for one visit: device emulation plus HAR and video recording."""
    context_options = {
        "record_har_path": str(output_directory / f"{site_name}.har"),
        "record_har_content": "omit",
        "record_har_mode": "full",
        "record_video_dir": str(output_directory),
    }
    if crawl_mode is CrawlMode.MOBILE:
        context_options.update(playwright.devices[MOBILE_DEVICE_NAME])
    return context_options


def visit_site(
    browser: Browser,
    playwright: Playwright,
    crawl_mode: CrawlMode,
    site_name: str,
    url: str,
    output_directory: Path,
    accept_words: list[str],
    waits: WaitSchedule = WaitSchedule(),
) -> VisitResult:
    """
    Visit one URL in a fresh context and write its HAR, screenshots and video to `output_directory`.

    `site_name` names the output files, so `ru.nl` gives `ru.nl.har`, `ru.nl_pre_consent.png`,
    `ru.nl_post_consent.png` (not in ignore mode) and `ru.nl.webm`.
    """
    output_directory.mkdir(parents=True, exist_ok=True)
    result = VisitResult(site_name=site_name)

    # TODO: block Disconnect-listed domains in CrawlMode.BLOCK
    context = browser.new_context(
        **build_context_options(playwright, crawl_mode, output_directory, site_name)
    )
    page = context.new_page()
    try:
        print(f"Crawling {site_name}...")
        page.goto(url)
        time.sleep(waits.after_page_load)
        page.screenshot(path=str(output_directory / f"{site_name}_pre_consent.png"), full_page=True)

        if crawl_mode.accepts_consent:
            result.consent_clicked = accept_cookies(page, accept_words)
            time.sleep(waits.after_consent)
            page.screenshot(
                path=str(output_directory / f"{site_name}_post_consent.png"), full_page=True
            )

        scroll_down(page)
        time.sleep(waits.after_scroll)
        result.final_url = page.url
    except Exception as visit_error:
        print(f"Error while crawling {site_name}: {visit_error}")
        result.error = f"{type(visit_error).__name__}: {visit_error}"
    finally:
        # Video path is only known before the page closes, and the file only exists after.
        video_path = page.video.path() if page.video else None
        page.close()
        context.close()
        if video_path:
            Path(video_path).rename(output_directory / f"{site_name}.webm")
    return result


# *******************************************
# Whole crawl
# *******************************************

def homepage_url(website_domain: str) -> str:
    return f"https://{website_domain}"


def crawl_sites(
    browser: Browser,
    playwright: Playwright,
    crawl_mode: CrawlMode,
    sites: list[tuple[str, str]],
    accept_words: list[str],
    output_directory: Path,
    crawled_list_path: Path,
    waits: WaitSchedule = WaitSchedule(),
    url_for_site: Callable[[str], str] = homepage_url,
) -> list[VisitResult]:
    """
    Visit every site not yet in the resume list, one at a time, and record each as done.

    `url_for_site` turns a site name into the URL to open. Tests swap it for a localhost builder.
    """
    results = []
    for website_domain, country_code in select_sites_to_crawl(sites, crawled_list_path):
        result = visit_site(
            browser,
            playwright,
            crawl_mode,
            website_domain,
            url_for_site(website_domain),
            output_directory,
            accept_words,
            waits,
        )
        add_to_crawled_list(crawled_list_path, website_domain, country_code)
        print(f"Finished crawling {website_domain}.")
        results.append(result)
    return results


def run_crawl(crawl_mode: CrawlMode, site_list_path: Path) -> None:
    """Launch one headful Chromium and crawl the site list in the given mode."""
    sites_to_crawl = read_site_list(site_list_path)
    accept_words = read_accept_words(ACCEPT_WORDS_PATH)
    print(f"Crawl mode: {crawl_mode.value}")
    print(f"Loaded {len(sites_to_crawl)} websites from {site_list_path}")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        crawl_sites(
            browser,
            playwright,
            crawl_mode,
            sites_to_crawl,
            accept_words,
            crawl_mode.output_directory,
            crawl_mode.crawled_list_path,
        )
        browser.close()


if __name__ == "__main__":
    command_line_arguments = parse_command_line_arguments()
    run_crawl(command_line_arguments.crawl_mode, command_line_arguments.site_list_path)
