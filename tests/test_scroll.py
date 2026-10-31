"""
Scrolling must reach the bottom of the homepage, in steps, and must give up on pages that never end.

Assignment: "scroll down to the bottom of the homepage in multiple steps".
"""

# Third party imports
from playwright.sync_api import Page

# Local package imports
from crawler import scroll_down

# Fixture page is 20 blocks of 500 px. Viewport is Playwright's default 1280x720.
TALL_PAGE_HEIGHT = 10_000

# Pauses zeroed. The pause is there to look human on real sites, not something the tests check.
NO_PAUSE = (0.0, 0.0)


def distance_from_bottom(page: Page) -> int:
    return page.evaluate(
        "() => document.documentElement.scrollHeight - (window.scrollY + window.innerHeight)"
    )


def test_scroll_reaches_bottom_of_tall_page(fresh_page: Page, fixture_server_url: str) -> None:
    fresh_page.goto(f"{fixture_server_url}/tall_page.html")
    assert fresh_page.evaluate("document.documentElement.scrollHeight") == TALL_PAGE_HEIGHT

    steps_taken = scroll_down(fresh_page, pause_seconds=NO_PAUSE)

    assert distance_from_bottom(fresh_page) <= 2
    # (10000 - 720) / 400 is 24 steps. A wheel event can land a few pixels short.
    assert 24 <= steps_taken <= 27


def test_scroll_on_short_page_takes_no_steps(fresh_page: Page, fixture_server_url: str) -> None:
    fresh_page.goto(f"{fixture_server_url}/no_banner.html")

    steps_taken = scroll_down(fresh_page, pause_seconds=NO_PAUSE)

    assert steps_taken == 0
    assert distance_from_bottom(fresh_page) <= 2


def test_scroll_gives_up_on_infinite_page(fresh_page: Page, fixture_server_url: str) -> None:
    fresh_page.goto(f"{fixture_server_url}/infinite_page.html")

    steps_taken = scroll_down(fresh_page, max_steps=30, pause_seconds=NO_PAUSE)

    assert steps_taken == 30
    # Page kept growing as we scrolled. That is what the cap is for.
    assert fresh_page.evaluate("document.documentElement.scrollHeight") > 1000
