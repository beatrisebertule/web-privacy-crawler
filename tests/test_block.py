"""
Block crawl. Requests to hosts in the five blocked Disconnect categories get no response.

Fixture page loads one pixel each from `ads.blocked.localhost`, `cdn.notblocked.localhost`
and `fonts.content.localhost`. Fixture list has `blocked.localhost` under Advertising and
Analytics, `content.localhost` under Content.
"""

# Standard library imports
import json
from pathlib import Path
from urllib.parse import urlsplit

# Third party imports
import pytest
from playwright.sync_api import Browser, Playwright

# Local package imports
from conftest import FIXTURES_DIRECTORY, NO_WAITS
from crawler import (
    BLOCKED_CATEGORIES,
    DISCONNECT_SERVICES_PATH,
    REPO_ROOT,
    CrawlMode,
    is_blocked,
    listed_categories,
    load_disconnect_categories,
    read_site_list,
    visit_site,
)

FIXTURE_SERVICES_PATH = FIXTURES_DIRECTORY / "disconnect_services.json"


@pytest.fixture(scope="module")
def fixture_categories() -> dict[str, frozenset[str]]:
    return load_disconnect_categories(FIXTURE_SERVICES_PATH)


@pytest.fixture(scope="module")
def real_categories() -> dict[str, frozenset[str]]:
    return load_disconnect_categories(DISCONNECT_SERVICES_PATH)


def pixel_statuses(har_path: Path) -> dict[str, int]:
    # Response status per pixel host. A host with no HAR entry is missing from the result.
    har = json.loads(har_path.read_text(encoding="utf-8"))
    return {
        urlsplit(entry["request"]["url"]).hostname: entry["response"]["status"]
        for entry in har["log"]["entries"]
        if entry["request"]["url"].endswith("/pixel.gif")
    }


def visit_third_party_page(
    crawl_mode: CrawlMode,
    headless_browser: Browser,
    playwright_instance: Playwright,
    fixture_server_url: str,
    categories_by_host: dict[str, frozenset[str]],
    output_directory: Path,
):
    return visit_site(
        headless_browser,
        playwright_instance,
        crawl_mode,
        "fixture.edu",
        f"{fixture_server_url}/third_party.html",
        output_directory,
        [],
        NO_WAITS,
        categories_by_host=categories_by_host,
    )


# *******************************************
# Loading and matching
# *******************************************

def test_loader_reads_categories_and_skips_flags(fixture_categories: dict[str, frozenset[str]]) -> None:
    assert fixture_categories == {
        "blocked.localhost": frozenset({"Advertising", "Analytics"}),
        "replay.localhost": frozenset({"Analytics"}),
        "content.localhost": frozenset({"Content"}),
    }


@pytest.mark.parametrize(
    ("hostname", "blocked"),
    [
        ("blocked.localhost", True),
        ("ads.blocked.localhost", True),
        ("Ads.Blocked.Localhost", True),
        ("replay.localhost", True),
        # Whole labels only.
        ("notblocked.localhost", False),
        ("blocked.localhost.example.edu", False),
        # Listed, but Content is not one of the five.
        ("fonts.content.localhost", False),
        ("localhost", False),
        ("", False),
    ],
)
def test_is_blocked(hostname: str, blocked: bool, fixture_categories: dict[str, frozenset[str]]) -> None:
    assert is_blocked(hostname, fixture_categories) is blocked


def test_listed_categories_of_subdomain(fixture_categories: dict[str, frozenset[str]]) -> None:
    assert listed_categories("ads.blocked.localhost", fixture_categories) == {"Advertising", "Analytics"}


# *******************************************
# Visits
# *******************************************

def test_block_visit_drops_listed_host_only(
    headless_browser: Browser,
    playwright_instance: Playwright,
    fixture_server_url: str,
    fixture_categories: dict[str, frozenset[str]],
    tmp_path: Path,
) -> None:
    result = visit_third_party_page(
        CrawlMode.BLOCK, headless_browser, playwright_instance, fixture_server_url, fixture_categories, tmp_path
    )

    statuses = pixel_statuses(tmp_path / "fixture.edu.har")
    assert result.succeeded
    assert result.blocked_requests == 1
    assert statuses.get("ads.blocked.localhost", 0) <= 0
    assert statuses["cdn.notblocked.localhost"] == 200
    assert statuses["fonts.content.localhost"] == 200


@pytest.mark.parametrize("crawl_mode", [CrawlMode.DESKTOP, CrawlMode.MOBILE, CrawlMode.IGNORE])
def test_other_modes_block_nothing(
    crawl_mode: CrawlMode,
    headless_browser: Browser,
    playwright_instance: Playwright,
    fixture_server_url: str,
    fixture_categories: dict[str, frozenset[str]],
    tmp_path: Path,
) -> None:
    # List passed on purpose. Only block mode may act on it.
    result = visit_third_party_page(
        crawl_mode, headless_browser, playwright_instance, fixture_server_url, fixture_categories, tmp_path
    )

    statuses = pixel_statuses(tmp_path / "fixture.edu.har")
    assert result.blocked_requests == 0
    assert statuses == {
        "ads.blocked.localhost": 200,
        "cdn.notblocked.localhost": 200,
        "fonts.content.localhost": 200,
    }


def test_block_mode_without_list_raises(
    headless_browser: Browser,
    playwright_instance: Playwright,
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError):
        visit_site(
            headless_browser,
            playwright_instance,
            CrawlMode.BLOCK,
            "fixture.edu",
            "http://127.0.0.1:1/",
            tmp_path,
            [],
            NO_WAITS,
        )
    assert not any(tmp_path.iterdir())


# *******************************************
# Real Disconnect list
# *******************************************

def test_real_list_has_every_blocked_category(real_categories: dict[str, frozenset[str]]) -> None:
    # Catches a typo in `BLOCKED_CATEGORIES`, or Disconnect renaming a category.
    all_categories = frozenset().union(*real_categories.values())
    assert BLOCKED_CATEGORIES <= all_categories


def test_real_list_blocks_known_examples(real_categories: dict[str, frozenset[str]]) -> None:
    blocked_host_count = sum(1 for categories in real_categories.values() if categories & BLOCKED_CATEGORIES)
    assert blocked_host_count > 1000
    assert is_blocked("stats.g.doubleclick.net", real_categories)
    assert is_blocked("adservice.google.com", real_categories)
    assert not is_blocked("www.google.com", real_categories)


def test_no_university_is_on_the_real_list(real_categories: dict[str, frozenset[str]]) -> None:
    sites = read_site_list(REPO_ROOT / "crawler_src" / "sites.csv")

    listed = [
        host
        for website_domain, _ in sites
        for host in (website_domain, f"www.{website_domain}")
        if is_blocked(host, real_categories)
    ]

    assert listed == []
