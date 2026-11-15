"""
Tests that `parse_referrer_policy` agrees with Chromium on each header.

Page server sends each case's Referrer-Policy. Page loads one image from its own server and one from a second server.
Some policies send the same pair of `Referer` values for the two images, which this can't tell apart.
Q11 only cares about `no-referrer`, and that sends nothing to either image.
"""

# Standard library imports
import enum
import importlib
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# Third party imports
import pytest
from playwright.sync_api import Page

# Import statement can't load a module name starting with a digit.
q11 = importlib.import_module("11_analysis")

ReferrerPolicy = q11.ReferrerPolicy
parse_referrer_policy = q11.parse_referrer_policy

PIXEL = (Path(__file__).resolve().parent / "fixtures" / "pixel.gif").read_bytes()


class RefererSent(enum.Enum):
    FULL = "full page URL"
    ORIGIN = "page origin"
    NONE = "no Referer"


# What each policy sends over plain HTTP.
# Without HTTPS there's no downgrade. Strict policies act like their plain versions.
SENT_BY_POLICY = {
    ReferrerPolicy.NO_REFERRER: (RefererSent.NONE, RefererSent.NONE),
    ReferrerPolicy.SAME_ORIGIN: (RefererSent.FULL, RefererSent.NONE),
    ReferrerPolicy.ORIGIN: (RefererSent.ORIGIN, RefererSent.ORIGIN),
    ReferrerPolicy.STRICT_ORIGIN: (RefererSent.ORIGIN, RefererSent.ORIGIN),
    ReferrerPolicy.ORIGIN_WHEN_CROSS_ORIGIN: (RefererSent.FULL, RefererSent.ORIGIN),
    ReferrerPolicy.STRICT_ORIGIN_WHEN_CROSS_ORIGIN: (RefererSent.FULL, RefererSent.ORIGIN),
    ReferrerPolicy.NO_REFERRER_WHEN_DOWNGRADE: (RefererSent.FULL, RefererSent.FULL),
    ReferrerPolicy.UNSAFE_URL: (RefererSent.FULL, RefererSent.FULL),
    # No policy. Chromium's default is `strict-origin-when-cross-origin`.
    None: (RefererSent.FULL, RefererSent.ORIGIN),
}

# Case id -> (header lines sent, effective policy expected)
CASES = {
    **{
        f"token-{policy.value}": ((policy.value,), policy)
        for policy in ReferrerPolicy
    },
    "no-header": ((), None),
    "fallback-overridden": (("no-referrer, strict-origin-when-cross-origin",), ReferrerPolicy.STRICT_ORIGIN_WHEN_CROSS_ORIGIN),
    "fallback-last": (("strict-origin-when-cross-origin, no-referrer",), ReferrerPolicy.NO_REFERRER),
    "unknown-after": (("no-referrer, made-up-policy",), ReferrerPolicy.NO_REFERRER),
    "unknown-only": (("made-up-policy",), None),
    "empty-value": (("",), None),
    "uppercase": (("NO-REFERRER",), ReferrerPolicy.NO_REFERRER),
    "mixed-case": (("Unsafe-URL",), ReferrerPolicy.UNSAFE_URL),
    "inner-whitespace": (("unsafe-url ,\tno-referrer",), ReferrerPolicy.NO_REFERRER),
    "two-lines": (("unsafe-url", "no-referrer"), ReferrerPolicy.NO_REFERRER),
    "empty-tokens": (("no-referrer,,",), ReferrerPolicy.NO_REFERRER),
    "quoted": (('"no-referrer"',), None),
    "trailing-semicolon": (("no-referrer;",), None),
}


class RefererRecorder(BaseHTTPRequestHandler):
    """Serves case pages and images, recording each request's `Referer` by path."""

    server: "RecordingServer"

    def do_GET(self) -> None:  # noqa: N802
        self.server.referers[self.path] = self.headers.get("Referer")
        if self.path.startswith("/page/"):
            case_id = self.path.removeprefix("/page/")
            header_lines, _expected = CASES[case_id]
            body = (
                f'<img src="/same/{case_id}">'
                f'<img src="{self.server.cross_origin_url}/cross/{case_id}">'
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            for value in header_lines:
                self.send_header("Referrer-Policy", value)
        else:
            body = PIXEL
            self.send_response(200)
            self.send_header("Content-Type", "image/gif")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        pass


class RecordingServer(ThreadingHTTPServer):
    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), RefererRecorder)
        self.referers: dict[str, str | None] = {}
        self.cross_origin_url = ""

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server_port}"


@pytest.fixture(scope="module")
def referer_servers() -> Iterator[tuple[RecordingServer, RecordingServer]]:
    """Page server and a second server on another port for cross-origin requests."""
    page_server = RecordingServer()
    cross_server = RecordingServer()
    page_server.cross_origin_url = cross_server.url
    for server in (page_server, cross_server):
        threading.Thread(target=server.serve_forever, daemon=True).start()
    yield page_server, cross_server
    for server in (page_server, cross_server):
        server.shutdown()
        server.server_close()


def classify(referer: str | None, page_url: str, page_origin: str) -> RefererSent:
    """
    Name what a `Referer` holds.

    :raises AssertionError: if it's neither the page URL nor its origin
    """
    if referer is None:
        return RefererSent.NONE
    if referer == page_url:
        return RefererSent.FULL
    if referer == f"{page_origin}/":
        return RefererSent.ORIGIN
    raise AssertionError(f"Referer fits no policy: {referer!r}")


@pytest.mark.parametrize("case_id", CASES)
def test_parser_matches_chromium(
    case_id: str,
    referer_servers: tuple[RecordingServer, RecordingServer],
    fresh_page: Page,
) -> None:
    page_server, cross_server = referer_servers
    header_lines, expected = CASES[case_id]
    page_url = f"{page_server.url}/page/{case_id}"

    fresh_page.goto(page_url, wait_until="load")

    # Request that never arrived is a failure, not "no Referer".
    same_path = f"/same/{case_id}"
    cross_path = f"/cross/{case_id}"
    assert same_path in page_server.referers, f"{same_path} never requested"
    assert cross_path in cross_server.referers, f"{cross_path} never requested"
    chromium_sent = (
        classify(page_server.referers[same_path], page_url, page_server.url),
        classify(cross_server.referers[cross_path], page_url, page_server.url),
    )

    assert chromium_sent == SENT_BY_POLICY[expected]
    assert parse_referrer_policy(list(header_lines)).effective == expected
