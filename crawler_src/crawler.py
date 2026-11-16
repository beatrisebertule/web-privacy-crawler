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
import json
import random
import re
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

# Third party imports
from playwright.sync_api import (
    Browser,
    Error as PlaywrightError,
    Locator,
    Page,
    Playwright,
    Route,
    sync_playwright,
)


# *******************************************
# Constants
# *******************************************

# Paths are relative to the repo root, not the working directory.
REPO_ROOT = Path(__file__).resolve().parent.parent
ACCEPT_WORDS_PATH = REPO_ROOT / "accept_words.txt"
# Phrases that just close the banner. They're only tried if no accept phrase matches,
# because closing a banner isn't consenting to it.
CLOSE_WORDS_PATH = REPO_ROOT / "close_words.txt"

MOBILE_DEVICE_NAME = "Pixel 10"

# Tracker blocking
# Copy of Disconnect's list is in this folder. Source and date in README.
DISCONNECT_SERVICES_PATH = Path(__file__).resolve().parent / "services.json"
BLOCKED_CATEGORIES = frozenset({
    "Advertising",
    "Analytics",
    "Social",
    "FingerprintingInvasive",
    "FingerprintingGeneral",
})

# Scrolling
# Half a desktop viewport per step gives lazy-loaded content time to appear.
# 200 steps is 80,000 px, taller than any homepage in `sites.csv`.
SCROLL_STEP_PIXELS = 400
SCROLL_MAX_STEPS = 200
SCROLL_PAUSE_SECONDS = (0.1, 0.3)

# Consent
CLICKABLE_SELECTOR = "button, a, [role=button], input[type=button], input[type=submit]"
CLICK_TIMEOUT_MILLISECONDS = 3000
# Columns of consent_clicks_<mode>.csv, in order.
CONSENT_CLICKS_HEADER = ("domain", "country", "match", "label", "phrase")

# Words that mark a button as a refusal or a settings link, matched whole against the
# normalized button text. Stops a substring match on "accept" from picking "accept necessary only".
REFUSAL_WORDS = (
    "necessary", "essential", "only", "required",
    "reject", "decline", "deny", "refuse", "disagree",
    "settings", "preferences", "manage", "customize", "customise", "options", "more",
    "weigeren", "noodzakelijk", "noodzakelijke", "alleen", "instellingen", "voorkeuren", "aanpassen",
)


class CrawlMode(enum.Enum):
    """
    Four crawl configurations from the assignment.

    Desktop, mobile and block accept the consent dialog.
    Ignore never touches it.
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
        # One resume file per mode. A shared one made the second crawl skip everything.
        return REPO_ROOT / f"crawled_{self.value}.txt"

    @property
    def consent_clicks_path(self) -> Path:
        # Kept out of crawl_data_<mode>/ because that folder goes into the hand-in zip as is.
        return REPO_ROOT / f"consent_clicks_{self.value}.csv"


@dataclass(frozen=True)
class WaitSchedule:
    """
    Seconds to sleep between crawl steps.

    Defaults are the assignment's schedule.
    page load -> 10 s -> accept -> 5 s -> scroll -> 5 s -> close
    Tests pass zeros.
    """

    after_page_load: float = 10.0
    after_consent: float = 5.0
    after_scroll: float = 5.0


class ConsentMatch(enum.Enum):
    """
    Which phrase list the clicked consent button came from.

    `FALLBACK` means no accept phrase matched, so the banner was only closed.
    """

    ACCEPT = "accept"
    FALLBACK = "fallback"


@dataclass(frozen=True)
class ButtonChoice:
    """
    Consent button picked by `choose_accept_button`.

    `label` is the button's text and `phrase` is the list entry it matched, both normalized.
    """

    locator: Locator
    label: str
    phrase: str
    match: ConsentMatch


@dataclass
class VisitResult:
    """
    Outcome of one visit. `error` is None on success.

    `first_attempt_error` is set when the bare domain never loaded and the visit was retried
    with www. Seen on yale.edu 2026-10-30. One of its five addresses served its host's
    certificate instead of one for yale.edu.
    """

    site_name: str
    final_url: str | None = None
    page_loaded: bool = False
    consent_match: ConsentMatch | None = None
    consent_label: str | None = None
    consent_phrase: str | None = None
    blocked_requests: int = 0
    error: str | None = None
    first_attempt_error: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.error is None

    @property
    def consent_clicked(self) -> bool:
        return self.consent_match is not None


# *******************************************
# Input files
# *******************************************

def parse_command_line_arguments() -> argparse.Namespace:
    """
    Parse `-m` and `-l` and check the site list exists.

    :return: Namespace with `crawl_mode` as a `CrawlMode` and `site_list_path` as a `Path`.
    :rtype: argparse.Namespace
    """
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
    Read the site list CSV.

    First row is a header. Empty and malformed rows are skipped.

    :param site_list_path: CSV with `domain,country,...` per line
    :return: `(website_domain, country_code)` pairs in file order, with country lowercased
    :rtype: list[tuple[str, str]]
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


def read_button_phrases(phrases_path: Path) -> list[str]:
    """
    Read one consent button phrase list, `accept_words.txt` or `close_words.txt`.

    :param phrases_path: text file, one phrase per line
    :return: Non-empty lines, stripped, in file order.
    :rtype: list[str]
    """
    with open(phrases_path, encoding="utf-8") as phrases_file:
        return [line.strip() for line in phrases_file if line.strip()]


# Never changes during a crawl, so it's read once here and used as the default below.
CLOSE_WORDS = read_button_phrases(CLOSE_WORDS_PATH)


# *******************************************
# Resume list
# *******************************************

def read_crawled_list(crawled_list_path: Path) -> set[tuple[str, str]]:
    """
    Read the resume list for one mode.

    :param crawled_list_path: CSV written by `add_to_crawled_list` (may not exist yet)
    :return: `(website_domain, country_code)` pairs already finished. Empty if no file.
    :rtype: set[tuple[str, str]]
    """
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
    """
    Append one finished site to the resume list.

    :param crawled_list_path: resume CSV for this mode, created on first write
    :param website_domain: as it appears in the site list
    :param country_code: two-letter code from the site list
    """
    with open(crawled_list_path, "a", newline="", encoding="utf-8") as crawled_list_file:
        csv.writer(crawled_list_file).writerow([website_domain, country_code])


def add_to_consent_clicks(
    consent_clicks_path: Path,
    website_domain: str,
    country_code: str,
    result: VisitResult,
) -> None:
    """
    Add a row saying what got clicked on one visit. Writes the header too if the file is new.

    example row: "ru.nl,nl,accept,accept all,accept all"
    example row: "lse.ac.uk,gb,none,," if nothing was clicked

    :param consent_clicks_path: click record for this mode, created on first write
    :param website_domain: as it appears in the site list
    :param country_code: two-letter code from the site list
    :param result: finished visit from `visit_site`
    """
    is_new_file = not consent_clicks_path.exists()
    row = {
        "domain": website_domain,
        "country": country_code,
        "match": result.consent_match.value if result.consent_match else "none",
        "label": result.consent_label or "",
        "phrase": result.consent_phrase or "",
    }
    # csv writes CRLF by default, even with newline="".
    with open(consent_clicks_path, "a", newline="", encoding="utf-8") as consent_clicks_file:
        writer = csv.writer(consent_clicks_file, lineterminator="\n")
        if is_new_file:
            writer.writerow(CONSENT_CLICKS_HEADER)
        writer.writerow([row[column] for column in CONSENT_CLICKS_HEADER])


def select_sites_to_crawl(
    sites: list[tuple[str, str]],
    crawled_list_path: Path,
) -> list[tuple[str, str]]:
    """
    Drop the sites already in the resume list.

    :param sites: `(website_domain, country_code)` pairs from `read_site_list`
    :param crawled_list_path: resume CSV for this mode
    :return: Remaining sites, in site list order.
    :rtype: list[tuple[str, str]]
    """
    already_crawled = read_crawled_list(crawled_list_path)
    return [site for site in sites if site not in already_crawled]


# *******************************************
# Page interaction
# *******************************************

def normalize_button_text(text: str) -> str:
    """
    Lowercase, drop punctuation and symbols, collapse whitespace. Keeps `&`.

    example: "  Accept All Cookies ✓ " -> "accept all cookies"

    :param text: button text as the page shows it
    :return: Normalized text, "" if nothing is left.
    :rtype: str
    """
    letters_and_spaces = re.sub(r"[^\w\s&]", " ", text.lower())
    return " ".join(letters_and_spaces.split())


def looks_like_a_refusal(normalized_text: str) -> bool:
    """
    Whole-word check against `REFUSAL_WORDS`. "non" in front of a word cancels it.

    example: "accept necessary only" -> True
    example: "accept non essential cookies" -> False
    example: "accept the essentials" -> False

    :param normalized_text: output of `normalize_button_text`
    :rtype: bool
    """
    words = normalized_text.split()
    return any(
        word in REFUSAL_WORDS and (index == 0 or words[index - 1] != "non")
        for index, word in enumerate(words)
    )


def contains_phrase(normalized_text: str, normalized_phrase: str) -> bool:
    """
    Whole-word phrase search.

    example: ("accept all cookies recommended", "accept all") -> True
    example: ("facebook", "ok") -> False

    :param normalized_text: output of `normalize_button_text`
    :param normalized_phrase: output of `normalize_button_text`
    :rtype: bool
    """
    return f" {normalized_phrase} " in f" {normalized_text} "


def collect_clickables(page: Page) -> list[tuple[Locator, str]]:
    """
    Gather every clickable in every frame with its normalized text.

    Visibility is not checked here. That is one round trip per element, and the caller
    only needs it for the few that match.

    Label is the first non-empty line of the element's text. A tile-style button carries its
    description under the label, and the label is what a visitor reads.

    :param page: page after load, frames included
    :return: `(locator, normalized_label)` pairs in frame and document order, without empty labels
    :rtype: list[tuple[Locator, str]]
    """
    clickables = []
    for frame in page.frames:
        candidates = frame.locator(CLICKABLE_SELECTOR)
        # One evaluate per frame, not one per element.
        texts = candidates.evaluate_all(
            "elements => elements.map(element =>"
            " element.innerText || element.value || element.getAttribute('aria-label') || '')"
        )
        for index, text in enumerate(texts):
            first_line = next((line for line in text.splitlines() if line.strip()), "")
            normalized = normalize_button_text(first_line)
            if normalized:
                clickables.append((candidates.nth(index), normalized))
    return clickables


def best_phrase_match(
    clickables: list[tuple[Locator, str]],
    phrases: list[str],
) -> tuple[Locator, str, str] | None:
    """
    Pick the clickable that best matches one phrase list.

    Two passes, longest phrase first in each.
    Pass 1 takes an exact match on the label.
    Pass 2 takes a whole-word match, skipping anything `looks_like_a_refusal`.
    Single-word phrases like "ok" and "complete" only count in pass 1.
    "Complete your application" is not consent.

    :param clickables: output of `collect_clickables`
    :param phrases: phrases from `read_button_phrases`, any case
    :return: `(locator, label, phrase)` for the best match, or None. Phrase is normalized.
    :rtype: tuple[Locator, str, str] | None
    """
    phrases_longest_first = sorted(
        {normalize_button_text(phrase) for phrase in phrases}, key=len, reverse=True
    )
    for phrase in phrases_longest_first:
        for locator, label in clickables:
            if label == phrase:
                return locator, label, phrase
    for phrase in phrases_longest_first:
        if " " not in phrase:
            continue
        for locator, label in clickables:
            if contains_phrase(label, phrase) and not looks_like_a_refusal(label):
                return locator, label, phrase
    return None


def choose_accept_button(
    clickables: list[tuple[Locator, str]],
    accept_words: list[str],
    close_words: list[str] = CLOSE_WORDS,
) -> ButtonChoice | None:
    """
    Pick the consent button to click. A dialogue-closing phrase is only used when no accept phrase 
    matches.

    example: labels "close" and "accept all cookies on this site" -> the accept button, `ACCEPT`

    :param clickables: output of `collect_clickables`
    :param accept_words: phrases from `accept_words.txt`
    :param close_words: close phrases, `close_words.txt` unless given
    :return: Chosen button, or None if neither list matches.
    :rtype: ButtonChoice | None
    """
    for phrases, match in ((accept_words, ConsentMatch.ACCEPT), (close_words, ConsentMatch.FALLBACK)):
        best = best_phrase_match(clickables, phrases)
        if best is not None:
            locator, label, phrase = best
            return ButtonChoice(locator, label, phrase, match)
    return None


def accept_cookies(
    page: Page,
    accept_words: list[str],
    close_words: list[str] = CLOSE_WORDS,
) -> ButtonChoice | None:
    """
    Click the consent dialog's accept button in any frame, or a close button if there isn't one.

    A hidden or unclickable best match is dropped and the next best tried.
    Every accept candidate is tried before any close candidate.

    :param page: page after load and the post-load wait
    :param accept_words: phrases from `accept_words.txt`
    :param close_words: close phrases, `close_words.txt` unless given
    :return: Button that got clicked, or None.
    :rtype: ButtonChoice | None
    """
    clickables = collect_clickables(page)
    while clickables:
        chosen = choose_accept_button(clickables, accept_words, close_words)
        if chosen is None:
            return None
        try:
            if chosen.locator.is_visible():
                chosen.locator.click(timeout=CLICK_TIMEOUT_MILLISECONDS)
                if chosen.match is ConsentMatch.ACCEPT:
                    print(f"Accepted cookies: \"{chosen.label}\"")
                else:
                    print(f"Closed consent dialog, no accept button (fallback): \"{chosen.label}\"")
                return chosen
        except PlaywrightError as click_error:
            # Covered by another element, detached, or the page navigated.
            print(f"Consent click failed, trying next candidate: {click_error}")
        clickables = [
            (locator, text) for locator, text in clickables
            if locator is not chosen.locator
        ]
    return None


def is_at_bottom(page: Page) -> bool:
    # Two pixels of slack for fractional scroll positions on scaled displays.
    return page.evaluate(
        "() => window.scrollY + window.innerHeight + 2 >= document.documentElement.scrollHeight"
    )


def scroll_down(
    page: Page,
    step_pixels: int = SCROLL_STEP_PIXELS,
    max_steps: int = SCROLL_MAX_STEPS,
    pause_seconds: tuple[float, float] = SCROLL_PAUSE_SECONDS,
) -> int:
    """
    Scroll to the bottom in fixed steps with a short random pause between them.

    Step cap is for pages that grow as you scroll.

    :param page: page to scroll
    :param step_pixels: wheel distance per step
    :param max_steps: give up after this many steps
    :param pause_seconds: `(low, high)` range for the pause after each step
    :return: Steps taken. Equals `max_steps` if the bottom was never reached.
    :rtype: int
    """
    for steps_taken in range(max_steps):
        if is_at_bottom(page):
            return steps_taken
        page.mouse.wheel(0, step_pixels)
        time.sleep(random.uniform(*pause_seconds))
    return max_steps


# *******************************************
# One visit
# *******************************************

def load_disconnect_categories(services_path: Path) -> dict[str, frozenset[str]]:
    """
    Read Disconnect's `services.json` into a map from hostname to categories.

    Entity entries also hold flags like `"session-replay": "true"`. Only list values are hostnames.

    example: "doubleclick.net" -> frozenset({"Advertising"})

    :param services_path: Disconnect's `services.json`
    :return: Every listed hostname with every category it is listed under.
    :rtype: dict[str, frozenset[str]]
    """
    with open(services_path, encoding="utf-8") as services_file:
        services = json.load(services_file)
    categories_by_host: dict[str, set[str]] = {}
    for category, entities in services["categories"].items():
        for entity in entities:
            for properties in entity.values():
                for hostnames in properties.values():
                    if not isinstance(hostnames, list):
                        continue
                    for hostname in hostnames:
                        categories_by_host.setdefault(hostname, set()).add(category)
    return {hostname: frozenset(categories) for hostname, categories in categories_by_host.items()}


def listed_categories(hostname: str, categories_by_host: dict[str, frozenset[str]]) -> frozenset[str]:
    """
    Categories of a hostname and of every listed parent domain of it.

    Matches whole labels only. "notdoubleclick.net" does not match "doubleclick.net".

    example: "stats.g.doubleclick.net" -> categories of "doubleclick.net"

    :param hostname: request hostname, no port
    :param categories_by_host: output of `load_disconnect_categories`
    :return: Union of the categories found, empty if none.
    :rtype: frozenset[str]
    """
    labels = hostname.lower().split(".")
    found: set[str] = set()
    for first_label in range(len(labels)):
        found |= categories_by_host.get(".".join(labels[first_label:]), frozenset())
    return frozenset(found)


def is_blocked(hostname: str, categories_by_host: dict[str, frozenset[str]]) -> bool:
    """
    Whether the block crawl drops requests to this hostname.

    :param hostname: request hostname, no port
    :param categories_by_host: output of `load_disconnect_categories`
    :rtype: bool
    """
    return bool(listed_categories(hostname, categories_by_host) & BLOCKED_CATEGORIES)


def build_context_options(
    playwright: Playwright,
    crawl_mode: CrawlMode,
    output_directory: Path,
    site_name: str,
) -> dict:
    """
    Context options for one visit.

    HAR and video recording always. Pixel 10 emulation in mobile mode.
    HAR content is omitted. Headers are all the analysis reads.

    :param playwright: running Playwright, for its device list
    :param crawl_mode: decides device emulation
    :param output_directory: where the HAR and video go
    :param site_name: names the HAR file
    :return: Keyword arguments for `browser.new_context`.
    :rtype: dict
    """
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
    categories_by_host: dict[str, frozenset[str]] | None = None,
    close_words: list[str] = CLOSE_WORDS,
) -> VisitResult:
    """
    Visit one URL in a fresh context. Writes HAR, screenshots and video.

    Output files for `site_name` "ru.nl":
    `ru.nl.har`, `ru.nl_pre_consent.png`, `ru.nl_post_consent.png`, `ru.nl.webm`
    Ignore mode writes no post-consent screenshot.
    Block mode aborts requests to hosts `is_blocked` says yes to. They get no response.

    :param browser: launched browser, shared across visits
    :param playwright: running Playwright, for the device list
    :param crawl_mode: which of the four crawls this is
    :param site_name: names the output files
    :param url: what to open
    :param output_directory: created if missing
    :param accept_words: phrases from `accept_words.txt`
    :param waits: sleeps between steps, assignment defaults
    :param categories_by_host: output of `load_disconnect_categories`. Required in block mode,
        ignored in the others.
    :param close_words: close phrases, `close_words.txt` unless given
    :return: Visit result, with `error` set if the visit failed partway
    :rtype: VisitResult
    """
    # Programming error, not a site failure. Raised before anything is written.
    if crawl_mode is CrawlMode.BLOCK and categories_by_host is None:
        raise ValueError("block mode needs categories_by_host, got None")

    output_directory.mkdir(parents=True, exist_ok=True)
    result = VisitResult(site_name=site_name)

    context = browser.new_context(
        **build_context_options(playwright, crawl_mode, output_directory, site_name)
    )
    if crawl_mode is CrawlMode.BLOCK:
        def abort_listed_hosts(route: Route) -> None:
            hostname = urlsplit(route.request.url).hostname or ""
            if is_blocked(hostname, categories_by_host):
                result.blocked_requests += 1
                route.abort("blockedbyclient")
            else:
                route.continue_()

        context.route("**/*", abort_listed_hosts)
    page = context.new_page()
    try:
        print(f"Crawling {site_name}...")
        page.goto(url)
        result.page_loaded = True
        time.sleep(waits.after_page_load)
        page.screenshot(path=str(output_directory / f"{site_name}_pre_consent.png"))

        if crawl_mode.accepts_consent:
            clicked = accept_cookies(page, accept_words, close_words)
            if clicked is not None:
                result.consent_match = clicked.match
                result.consent_label = clicked.label
                result.consent_phrase = clicked.phrase
            time.sleep(waits.after_consent)
            page.screenshot(path=str(output_directory / f"{site_name}_post_consent.png"))

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
            # Overwrites a failed earlier attempt's video. Plain rename fails on Windows if the file exists.
            Path(video_path).replace(output_directory / f"{site_name}.webm")
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
    categories_by_host: dict[str, frozenset[str]] | None = None,
    consent_clicks_path: Path | None = None,
    close_words: list[str] = CLOSE_WORDS,
) -> list[VisitResult]:
    """
    Visit every site not yet in the resume list, one at a time, and record each success as done.

    :param browser: launched browser, shared across visits
    :param playwright: running Playwright
    :param crawl_mode: which of the four crawls this is
    :param sites: `(website_domain, country_code)` pairs from `read_site_list`
    :param accept_words: phrases from `accept_words.txt`
    :param output_directory: where every visit writes its files
    :param crawled_list_path: resume CSV for this mode
    :param waits: sleeps between steps, assignment defaults
    :param url_for_site: site name to URL. Tests point it at localhost.
    :param categories_by_host: output of `load_disconnect_categories`, required in block mode
    :param consent_clicks_path: click record for this mode, or None to skip it.
        Starts fresh if there's no resume list yet.
    :param close_words: close phrases, `close_words.txt` unless given
    :return: One result per site visited this run.
    :rtype: list[VisitResult]
    """
    # No resume list means the whole list gets crawled again, so old click rows would be duplicates.
    if (
        crawl_mode.accepts_consent
        and consent_clicks_path is not None
        and consent_clicks_path.exists()
        and not crawled_list_path.exists()
    ):
        print(f"No {crawled_list_path.name}, so starting {consent_clicks_path.name} fresh")
        consent_clicks_path.unlink()
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
            categories_by_host=categories_by_host,
            close_words=close_words,
        )
        # Bare domain that never loaded gets one retry with www. Files keep the list's name.
        if not result.page_loaded and not website_domain.startswith("www."):
            first_attempt_error = result.error
            print(f"{website_domain} did not load, retrying as www.{website_domain}")
            result = visit_site(
                browser,
                playwright,
                crawl_mode,
                website_domain,
                url_for_site(f"www.{website_domain}"),
                output_directory,
                accept_words,
                waits,
                categories_by_host=categories_by_host,
                close_words=close_words,
            )
            result.first_attempt_error = first_attempt_error
        # Failed visits stay out of resume list, next run retries.
        if result.succeeded:
            add_to_crawled_list(crawled_list_path, website_domain, country_code)
            if crawl_mode.accepts_consent and consent_clicks_path is not None:
                add_to_consent_clicks(consent_clicks_path, website_domain, country_code, result)
        print(f"Finished crawling {website_domain}.")
        results.append(result)
    return results


def run_crawl(crawl_mode: CrawlMode, site_list_path: Path) -> None:
    """
    Launch one headful Chromium and crawl the site list in the given mode.

    Headful because some consent platforms serve nothing to a headless browser.

    :param crawl_mode: which of the four crawls to run
    :param site_list_path: CSV for `read_site_list`
    """
    sites_to_crawl = read_site_list(site_list_path)
    accept_words = read_button_phrases(ACCEPT_WORDS_PATH)
    print(f"Crawl mode: {crawl_mode.value}")
    print(f"Loaded {len(sites_to_crawl)} websites from {site_list_path}")
    remaining_count = len(select_sites_to_crawl(sites_to_crawl, crawl_mode.crawled_list_path))
    print(
        f"{len(sites_to_crawl) - remaining_count} already done in {crawl_mode.crawled_list_path.name}, "
        f"{remaining_count} to crawl"
    )
    if crawl_mode.accepts_consent:
        print(f"Consent clicks recorded in {crawl_mode.consent_clicks_path.name}")

    categories_by_host = None
    if crawl_mode is CrawlMode.BLOCK:
        categories_by_host = load_disconnect_categories(DISCONNECT_SERVICES_PATH)
        blocked_host_count = sum(
            1 for categories in categories_by_host.values() if categories & BLOCKED_CATEGORIES
        )
        print(f"Blocking {blocked_host_count} hostnames from {DISCONNECT_SERVICES_PATH.name}")

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
            categories_by_host=categories_by_host,
            consent_clicks_path=crawl_mode.consent_clicks_path,
        )
        browser.close()


if __name__ == "__main__":
    # Piped output on Windows is cp1252. A character it can't encode in an error message
    # must not end the crawl.
    sys.stdout.reconfigure(errors="backslashreplace")
    command_line_arguments = parse_command_line_arguments()
    run_crawl(command_line_arguments.crawl_mode, command_line_arguments.site_list_path)
