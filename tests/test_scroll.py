"""
Scrolling must reach the bottom of the homepage, in steps.

Assignment: "scroll down to the bottom of the homepage in multiple steps".
"""

# Third party imports
import pytest
from playwright.sync_api import Page

# Local package imports
from crawler import scroll_down

# Fixture page is 20 blocks of 500 px. Viewport is Playwright's default 1280x720.
TALL_PAGE_HEIGHT = 10_000


def distance_from_bottom(page: Page) -> int:
    return page.evaluate(
        "() => document.documentElement.scrollHeight - (window.scrollY + window.innerHeight)"
    )


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="scroll_down exits with 20% chance per step and averages ~430 px on a 10000 px page",
)
def test_scroll_reaches_bottom_of_tall_page(fresh_page: Page, fixture_server_url: str) -> None:
    fresh_page.goto(f"{fixture_server_url}/tall_page.html")
    assert fresh_page.evaluate("document.documentElement.scrollHeight") == TALL_PAGE_HEIGHT

    scroll_down(fresh_page)

    assert distance_from_bottom(fresh_page) <= 100


def test_scroll_on_short_page_does_not_hang(fresh_page: Page, fixture_server_url: str) -> None:
    fresh_page.goto(f"{fixture_server_url}/no_banner.html")

    scroll_down(fresh_page)

    assert distance_from_bottom(fresh_page) <= 100
