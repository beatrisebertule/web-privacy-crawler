"""
Consent handling against local banner pages.

Each fixture button writes `clicked:<its text>` into the document title, so a test can read
back exactly which element got clicked, or that nothing did.
"""

# Third party imports
import pytest
from playwright.sync_api import Page

# Local package imports
from crawler import ACCEPT_WORDS_PATH, accept_cookies, read_accept_words


@pytest.fixture(scope="module")
def accept_words() -> list[str]:
    return read_accept_words(ACCEPT_WORDS_PATH)


def test_accept_words_file_is_non_empty_and_stripped(accept_words: list[str]) -> None:
    assert accept_words
    assert all(word == word.strip() and word for word in accept_words)


def test_clicks_single_accept_button(
    fresh_page: Page, fixture_server_url: str, accept_words: list[str]
) -> None:
    fresh_page.goto(f"{fixture_server_url}/banner_button.html")

    clicked = accept_cookies(fresh_page, accept_words)

    assert clicked
    assert fresh_page.title() == "clicked:Accept all cookies"


def test_no_banner_clicks_nothing(
    fresh_page: Page, fixture_server_url: str, accept_words: list[str]
) -> None:
    fresh_page.goto(f"{fixture_server_url}/no_banner.html")

    clicked = accept_cookies(fresh_page, accept_words)

    assert not clicked
    assert fresh_page.title() == "no banner"


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="bare 'accept' precedes 'accept all' in accept_words.txt and has-text is a substring match",
)
def test_prefers_accept_all_over_accept_necessary(
    fresh_page: Page, fixture_server_url: str, accept_words: list[str]
) -> None:
    fresh_page.goto(f"{fixture_server_url}/banner_decoy.html")

    accept_cookies(fresh_page, accept_words)

    assert fresh_page.title() == "clicked:Accept all"


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="accept_cookies only looks at <button> elements")
def test_clicks_link_styled_as_button(
    fresh_page: Page, fixture_server_url: str, accept_words: list[str]
) -> None:
    fresh_page.goto(f"{fixture_server_url}/banner_link.html")

    clicked = accept_cookies(fresh_page, accept_words)

    assert clicked
    assert fresh_page.title() == "clicked:Accept all cookies"


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="accept_cookies does not look inside iframes")
def test_clicks_button_inside_iframe(
    fresh_page: Page, fixture_server_url: str, accept_words: list[str]
) -> None:
    fresh_page.goto(f"{fixture_server_url}/banner_iframe.html")

    clicked = accept_cookies(fresh_page, accept_words)

    assert clicked
    # Button lives in the child frame.
    child_frame = next(frame for frame in fresh_page.frames if frame.url.endswith("banner_button.html"))
    assert child_frame.title() == "clicked:Accept all cookies"
