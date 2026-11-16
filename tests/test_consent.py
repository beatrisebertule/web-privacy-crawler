"""
Consent handling against local banner pages.

Each fixture button writes `clicked:<its text>` into the document title.
A test reads the title back to see which element got clicked, or that nothing did.
"""

# Standard library imports
from pathlib import Path

# Third party imports
import pytest
from playwright.sync_api import Page

# Local package imports
from crawler import (
    ACCEPT_WORDS_PATH,
    CLOSE_WORDS,
    CLOSE_WORDS_PATH,
    accept_cookies,
    looks_like_a_refusal,
    normalize_button_text,
    read_button_phrases,
)


@pytest.fixture(scope="module")
def accept_words() -> list[str]:
    return read_button_phrases(ACCEPT_WORDS_PATH)


@pytest.mark.parametrize("phrases_path", [ACCEPT_WORDS_PATH, CLOSE_WORDS_PATH])
def test_phrase_file_is_non_empty_and_stripped(phrases_path: Path) -> None:
    phrases = read_button_phrases(phrases_path)

    assert phrases
    assert all(phrase == phrase.strip() and phrase for phrase in phrases)


def test_phrase_files_do_not_overlap(accept_words: list[str]) -> None:
    # Phrase in both files would be tried as an accept and never reach the fallback.
    normalized_accept = {normalize_button_text(phrase) for phrase in accept_words}
    normalized_close = {normalize_button_text(phrase) for phrase in CLOSE_WORDS}

    assert "close" in normalized_close
    assert normalized_accept.isdisjoint(normalized_close)


@pytest.mark.parametrize(
    ("raw_text", "normalized"),
    [
        ("  Accept All Cookies ✓ ", "accept all cookies"),
        ("ACCEPT\n&\nCLOSE", "accept & close"),
        ("Alles accepteren!", "alles accepteren"),
        ("", ""),
    ],
)
def test_normalize_button_text(raw_text: str, normalized: str) -> None:
    assert normalize_button_text(raw_text) == normalized


@pytest.mark.parametrize(
    ("normalized_text", "is_refusal"),
    [
        ("accept necessary only", True),
        ("cookie settings", True),
        ("alleen noodzakelijke cookies", True),
        ("reject non essential cookies", True),
        ("accept all cookies", False),
        ("ok", False),
        # Whole words only. "essentials" is not "essential".
        ("accept the essentials", False),
        # "non" cancels the word after it.
        ("accept non essential cookies", False),
    ],
)
def test_looks_like_a_refusal(normalized_text: str, is_refusal: bool) -> None:
    assert looks_like_a_refusal(normalized_text) is is_refusal


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


def test_prefers_accept_all_over_accept_necessary(
    fresh_page: Page, fixture_server_url: str, accept_words: list[str]
) -> None:
    fresh_page.goto(f"{fixture_server_url}/banner_decoy.html")

    accept_cookies(fresh_page, accept_words)

    assert fresh_page.title() == "clicked:Accept all"


def test_substring_match_skips_refusal_wording(
    fresh_page: Page, fixture_server_url: str, accept_words: list[str]
) -> None:
    fresh_page.goto(f"{fixture_server_url}/banner_substring.html")

    accept_cookies(fresh_page, accept_words)

    assert fresh_page.title() == "clicked:Accept all cookies (recommended)"


def test_refusal_only_banner_is_left_alone(
    fresh_page: Page, fixture_server_url: str, accept_words: list[str]
) -> None:
    fresh_page.goto(f"{fixture_server_url}/banner_refusal_only.html")

    clicked = accept_cookies(fresh_page, accept_words)

    assert not clicked
    assert fresh_page.title() == "banner with only refusal buttons"


def test_tile_chooser_picks_the_complete_tile(
    fresh_page: Page, fixture_server_url: str, accept_words: list[str]
) -> None:
    fresh_page.goto(f"{fixture_server_url}/banner_tiles.html")

    accept_cookies(fresh_page, accept_words)

    assert fresh_page.title() == "clicked:Complete"


def test_accepts_non_essential_over_reject_non_essential(
    fresh_page: Page, fixture_server_url: str, accept_words: list[str]
) -> None:
    fresh_page.goto(f"{fixture_server_url}/banner_non_essential.html")

    accept_cookies(fresh_page, accept_words)

    assert fresh_page.title() == "clicked:Accept Non-Essential Cookies"


def test_accepts_recommended_settings_over_reject_all(
    fresh_page: Page, fixture_server_url: str, accept_words: list[str]
) -> None:
    fresh_page.goto(f"{fixture_server_url}/banner_recommended.html")

    accept_cookies(fresh_page, accept_words)

    assert fresh_page.title() == "clicked:Accept recommended settings"


def test_clicks_link_styled_as_button(
    fresh_page: Page, fixture_server_url: str, accept_words: list[str]
) -> None:
    fresh_page.goto(f"{fixture_server_url}/banner_link.html")

    clicked = accept_cookies(fresh_page, accept_words)

    assert clicked
    assert fresh_page.title() == "clicked:Accept all cookies"


def test_clicks_button_inside_iframe(
    fresh_page: Page, fixture_server_url: str, accept_words: list[str]
) -> None:
    fresh_page.goto(f"{fixture_server_url}/banner_iframe.html")

    clicked = accept_cookies(fresh_page, accept_words)

    assert clicked
    # Button lives in the child frame.
    child_frame = next(frame for frame in fresh_page.frames if frame.url.endswith("banner_button.html"))
    assert child_frame.title() == "clicked:Accept all cookies"
