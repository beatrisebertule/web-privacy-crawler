"""
One visit must leave exactly the files the hand-in zip expects, named after the site.

    <site>.har, <site>_pre_consent.png, <site>_post_consent.png (not in ignore), <site>.webm
"""

# Standard library imports
import csv
import json
from pathlib import Path

# Third party imports
import pytest
from playwright.sync_api import Browser, Playwright

# Local package imports
from conftest import FIXTURES_DIRECTORY, NO_WAITS
from crawl import (
    ACCEPT_WORDS_PATH,
    CONSENT_CLICKS_HEADER,
    CrawlMode,
    crawl_sites,
    load_disconnect_categories,
    read_button_phrases,
    visit_site,
)


@pytest.fixture(scope="module")
def accept_words() -> list[str]:
    return read_button_phrases(ACCEPT_WORDS_PATH)


@pytest.fixture(scope="module")
def fixture_categories() -> dict[str, frozenset[str]]:
    return load_disconnect_categories(FIXTURES_DIRECTORY / "disconnect_services.json")


def output_names(output_directory: Path) -> set[str]:
    return {path.name for path in output_directory.iterdir()}


@pytest.mark.parametrize("crawl_mode", [CrawlMode.DESKTOP, CrawlMode.MOBILE, CrawlMode.BLOCK])
def test_consent_modes_write_four_files(
    crawl_mode: CrawlMode,
    headless_browser: Browser,
    playwright_instance: Playwright,
    fixture_server_url: str,
    accept_words: list[str],
    fixture_categories: dict[str, frozenset[str]],
    tmp_path: Path,
) -> None:
    result = visit_site(
        headless_browser,
        playwright_instance,
        crawl_mode,
        "fixture.edu",
        f"{fixture_server_url}/banner_button.html",
        tmp_path,
        accept_words,
        NO_WAITS,
        categories_by_host=fixture_categories,
    )

    assert result.succeeded
    assert result.consent_clicked
    assert result.final_url == f"{fixture_server_url}/banner_button.html"
    assert output_names(tmp_path) == {
        "fixture.edu.har",
        "fixture.edu_pre_consent.png",
        "fixture.edu_post_consent.png",
        "fixture.edu.webm",
    }


def test_ignore_mode_writes_no_post_consent_screenshot_and_never_clicks(
    headless_browser: Browser,
    playwright_instance: Playwright,
    fixture_server_url: str,
    accept_words: list[str],
    tmp_path: Path,
) -> None:
    result = visit_site(
        headless_browser,
        playwright_instance,
        CrawlMode.IGNORE,
        "fixture.edu",
        f"{fixture_server_url}/banner_button.html",
        tmp_path,
        accept_words,
        NO_WAITS,
    )

    assert result.succeeded
    assert not result.consent_clicked
    assert output_names(tmp_path) == {
        "fixture.edu.har",
        "fixture.edu_pre_consent.png",
        "fixture.edu.webm",
    }


def png_size(png_path: Path) -> tuple[int, int]:
    # Width and height are bytes 16 to 24 of a PNG header.
    header = png_path.read_bytes()[16:24]
    return int.from_bytes(header[:4], "big"), int.from_bytes(header[4:], "big")


def test_screenshots_are_viewport_not_full_page(
    headless_browser: Browser,
    playwright_instance: Playwright,
    fixture_server_url: str,
    accept_words: list[str],
    tmp_path: Path,
) -> None:
    # Fixture page is 10000 px tall. Playwright's default viewport is 1280x720.
    visit_site(
        headless_browser,
        playwright_instance,
        CrawlMode.DESKTOP,
        "fixture.edu",
        f"{fixture_server_url}/tall_page.html",
        tmp_path,
        accept_words,
        NO_WAITS,
    )

    assert png_size(tmp_path / "fixture.edu_pre_consent.png") == (1280, 720)
    assert png_size(tmp_path / "fixture.edu_post_consent.png") == (1280, 720)


def test_har_records_the_page_request(
    headless_browser: Browser,
    playwright_instance: Playwright,
    fixture_server_url: str,
    accept_words: list[str],
    tmp_path: Path,
) -> None:
    visit_site(
        headless_browser,
        playwright_instance,
        CrawlMode.DESKTOP,
        "fixture.edu",
        f"{fixture_server_url}/no_banner.html",
        tmp_path,
        accept_words,
        NO_WAITS,
    )

    har = json.loads((tmp_path / "fixture.edu.har").read_text(encoding="utf-8"))
    requested_urls = [entry["request"]["url"] for entry in har["log"]["entries"]]
    assert f"{fixture_server_url}/no_banner.html" in requested_urls


def test_mobile_mode_sends_pixel_user_agent(
    headless_browser: Browser,
    playwright_instance: Playwright,
    fixture_server_url: str,
    accept_words: list[str],
    tmp_path: Path,
) -> None:
    visit_site(
        headless_browser,
        playwright_instance,
        CrawlMode.MOBILE,
        "fixture.edu",
        f"{fixture_server_url}/no_banner.html",
        tmp_path,
        accept_words,
        NO_WAITS,
    )

    # Sites pick their mobile variant from the User-Agent header.
    # Screenshot width is no good here. A page without a viewport meta tag lays out at 980 CSS px.
    har = json.loads((tmp_path / "fixture.edu.har").read_text(encoding="utf-8"))
    page_entry = next(
        entry for entry in har["log"]["entries"]
        if entry["request"]["url"] == f"{fixture_server_url}/no_banner.html"
    )
    user_agent = next(
        header["value"] for header in page_entry["request"]["headers"]
        if header["name"].lower() == "user-agent"
    )
    assert user_agent == playwright_instance.devices["Pixel 10"]["user_agent"]
    assert "Android" in user_agent and "Mobile" in user_agent


def test_unreachable_site_is_reported_not_raised(
    headless_browser: Browser,
    playwright_instance: Playwright,
    accept_words: list[str],
    tmp_path: Path,
) -> None:
    result = visit_site(
        headless_browser,
        playwright_instance,
        CrawlMode.DESKTOP,
        "nowhere.invalid",
        "http://127.0.0.1:1/",
        tmp_path,
        accept_words,
        NO_WAITS,
    )

    assert not result.succeeded
    assert result.error is not None


def test_failed_visit_is_not_marked_as_crawled(
    headless_browser: Browser,
    playwright_instance: Playwright,
    accept_words: list[str],
    tmp_path: Path,
) -> None:
    crawled_list_path = tmp_path / "crawled.txt"

    crawl_sites(
        headless_browser,
        playwright_instance,
        CrawlMode.DESKTOP,
        [("nowhere.invalid", "nl")],
        accept_words,
        tmp_path / "out",
        crawled_list_path,
        NO_WAITS,
        url_for_site=lambda _: "http://127.0.0.1:1/",
    )

    assert not crawled_list_path.exists() or crawled_list_path.read_text() == ""


def test_crawl_sites_visits_each_site_once_and_records_it(
    headless_browser: Browser,
    playwright_instance: Playwright,
    fixture_server_url: str,
    accept_words: list[str],
    tmp_path: Path,
) -> None:
    crawled_list_path = tmp_path / "crawled.txt"
    sites = [("one.edu", "us"), ("two.ac.uk", "uk")]

    first_run = crawl_sites(
        headless_browser,
        playwright_instance,
        CrawlMode.DESKTOP,
        sites,
        accept_words,
        tmp_path / "out",
        crawled_list_path,
        NO_WAITS,
        url_for_site=lambda _: f"{fixture_server_url}/no_banner.html",
    )
    second_run = crawl_sites(
        headless_browser,
        playwright_instance,
        CrawlMode.DESKTOP,
        sites,
        accept_words,
        tmp_path / "out",
        crawled_list_path,
        NO_WAITS,
        url_for_site=lambda _: f"{fixture_server_url}/no_banner.html",
    )

    assert [result.site_name for result in first_run] == ["one.edu", "two.ac.uk"]
    assert second_run == []
    assert (tmp_path / "out" / "one.edu.har").is_file()
    assert (tmp_path / "out" / "two.ac.uk.webm").is_file()


# *******************************************
# www retry
# *******************************************

UNREACHABLE_URL = "http://127.0.0.1:1/"


def test_bare_domain_that_fails_is_retried_with_www(
    headless_browser: Browser,
    playwright_instance: Playwright,
    fixture_server_url: str,
    accept_words: list[str],
    tmp_path: Path,
) -> None:
    # Bare name unreachable, www name serves the fixture page.
    requested_names = []

    def url_for_site(site_name: str) -> str:
        requested_names.append(site_name)
        return f"{fixture_server_url}/banner_button.html" if site_name.startswith("www.") else UNREACHABLE_URL

    crawled_list_path = tmp_path / "crawled.txt"
    results = crawl_sites(
        headless_browser,
        playwright_instance,
        CrawlMode.DESKTOP,
        [("fixture.edu", "us")],
        accept_words,
        tmp_path / "out",
        crawled_list_path,
        NO_WAITS,
        url_for_site=url_for_site,
    )

    assert requested_names == ["fixture.edu", "www.fixture.edu"]
    assert results[0].succeeded
    assert results[0].first_attempt_error is not None
    assert results[0].final_url == f"{fixture_server_url}/banner_button.html"
    assert output_names(tmp_path / "out") == {
        "fixture.edu.har",
        "fixture.edu_pre_consent.png",
        "fixture.edu_post_consent.png",
        "fixture.edu.webm",
    }
    assert crawled_list_path.read_text(encoding="utf-8").strip() == "fixture.edu,us"


def test_site_failing_with_and_without_www_is_not_marked(
    headless_browser: Browser,
    playwright_instance: Playwright,
    accept_words: list[str],
    tmp_path: Path,
) -> None:
    requested_names = []

    def url_for_site(site_name: str) -> str:
        requested_names.append(site_name)
        return UNREACHABLE_URL

    crawled_list_path = tmp_path / "crawled.txt"
    results = crawl_sites(
        headless_browser,
        playwright_instance,
        CrawlMode.DESKTOP,
        [("nowhere.invalid", "nl")],
        accept_words,
        tmp_path / "out",
        crawled_list_path,
        NO_WAITS,
        url_for_site=url_for_site,
    )

    assert requested_names == ["nowhere.invalid", "www.nowhere.invalid"]
    assert not results[0].succeeded
    assert not crawled_list_path.exists()


def test_site_that_loads_is_not_retried(
    headless_browser: Browser,
    playwright_instance: Playwright,
    fixture_server_url: str,
    accept_words: list[str],
    tmp_path: Path,
) -> None:
    requested_names = []

    def url_for_site(site_name: str) -> str:
        requested_names.append(site_name)
        return f"{fixture_server_url}/no_banner.html"

    results = crawl_sites(
        headless_browser,
        playwright_instance,
        CrawlMode.DESKTOP,
        [("fixture.edu", "us")],
        accept_words,
        tmp_path / "out",
        tmp_path / "crawled.txt",
        NO_WAITS,
        url_for_site=url_for_site,
    )

    assert requested_names == ["fixture.edu"]
    assert results[0].first_attempt_error is None


def read_consent_clicks(consent_clicks_path: Path) -> list[list[str]]:
    # Not DictReader, which drops a repeated column name without an error.
    with open(consent_clicks_path, newline="", encoding="utf-8") as consent_clicks_file:
        return list(csv.reader(consent_clicks_file))


@pytest.mark.parametrize(
    ("fixture_page", "expected_row"),
    [
        ("banner_button.html", ["fixture.edu", "nl", "accept", "accept all cookies", "accept all cookies"]),
        ("banner_close_only.html", ["fixture.edu", "nl", "fallback", "close", "close"]),
        ("no_banner.html", ["fixture.edu", "nl", "none", "", ""]),
    ],
)
def test_consent_clicks_records_what_was_clicked(
    fixture_page: str,
    expected_row: list[str],
    headless_browser: Browser,
    playwright_instance: Playwright,
    fixture_server_url: str,
    accept_words: list[str],
    tmp_path: Path,
) -> None:
    consent_clicks_path = tmp_path / "consent_clicks.csv"

    crawl_sites(
        headless_browser,
        playwright_instance,
        CrawlMode.DESKTOP,
        [("fixture.edu", "nl")],
        accept_words,
        tmp_path / "out",
        tmp_path / "crawled.txt",
        NO_WAITS,
        url_for_site=lambda _: f"{fixture_server_url}/{fixture_page}",
        consent_clicks_path=consent_clicks_path,
    )

    assert read_consent_clicks(consent_clicks_path) == [list(CONSENT_CLICKS_HEADER), expected_row]
    # The crawl folder goes into the hand-in zip as is, so the CSV mustn't land there.
    assert not any(path.suffix == ".csv" for path in (tmp_path / "out").iterdir())
