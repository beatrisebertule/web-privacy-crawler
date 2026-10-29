"""
One visit must leave exactly the files the hand-in zip expects, named after the site.

    <site>.har, <site>_pre_consent.png, <site>_post_consent.png (not in ignore), <site>.webm
"""

# Standard library imports
import json
from pathlib import Path

# Third party imports
import pytest
from playwright.sync_api import Browser, Playwright

# Local package imports
from conftest import NO_WAITS
from crawler import ACCEPT_WORDS_PATH, CrawlMode, crawl_sites, read_accept_words, visit_site


@pytest.fixture(scope="module")
def accept_words() -> list[str]:
    return read_accept_words(ACCEPT_WORDS_PATH)


def output_names(output_directory: Path) -> set[str]:
    return {path.name for path in output_directory.iterdir()}


@pytest.mark.parametrize("crawl_mode", [CrawlMode.DESKTOP, CrawlMode.MOBILE, CrawlMode.BLOCK])
def test_consent_modes_write_four_files(
    crawl_mode: CrawlMode,
    headless_browser: Browser,
    playwright_instance: Playwright,
    fixture_server_url: str,
    accept_words: list[str],
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
    # Screenshot width is no good here: a page without a viewport meta tag lays out at 980 CSS px.
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


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="crawl_sites marks a site as crawled even when the visit failed")
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
