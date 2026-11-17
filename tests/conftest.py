"""
Shared fixtures. A local web server for the fixture pages and one headless browser.

Fixture names avoid `page`, `browser` and `playwright`. pytest-playwright claims those names
and clashes with them when installed.
"""

# Standard library imports
import sys
import threading
from collections.abc import Iterator
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# Third party imports
import pytest
from playwright.sync_api import Browser, Page, Playwright, sync_playwright

# Local package imports
# crawler_src is not a package. Path entry instead of an install.
TESTS_DIRECTORY = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS_DIRECTORY.parent / "crawler_src"))
# Analysis scripts import siblings by name, tests need folder on same path
sys.path.insert(0, str(TESTS_DIRECTORY.parent / "analysis"))

from crawl import WaitSchedule  # noqa: E402

FIXTURES_DIRECTORY = TESTS_DIRECTORY / "fixtures"

# Every wait zeroed. Schedule is the assignment's, not something the tests check.
NO_WAITS = WaitSchedule(after_page_load=0, after_consent=0, after_scroll=0)


class QuietRequestHandler(SimpleHTTPRequestHandler):
    """Serves the fixtures folder without logging every request to stderr."""

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        pass


@pytest.fixture(scope="session")
def fixture_server_url() -> Iterator[str]:
    """Serve `tests/fixtures/` on an ephemeral localhost port for the whole session."""
    handler = partial(QuietRequestHandler, directory=str(FIXTURES_DIRECTORY))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


@pytest.fixture(scope="session")
def playwright_instance() -> Iterator[Playwright]:
    with sync_playwright() as playwright:
        yield playwright


@pytest.fixture(scope="session")
def headless_browser(playwright_instance: Playwright) -> Iterator[Browser]:
    browser = playwright_instance.chromium.launch(headless=True)
    yield browser
    browser.close()


@pytest.fixture
def fresh_page(headless_browser: Browser) -> Iterator[Page]:
    """A page in its own context, thrown away after the test."""
    context = headless_browser.new_context()
    page = context.new_page()
    yield page
    context.close()
