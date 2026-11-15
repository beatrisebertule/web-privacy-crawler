"""
Tests for picking the Q10/Q11 HAR entries.

Exclusion tests all have at least one valid response that doesn't get excluded
"""

# Standard library imports
import json
from pathlib import Path

# Third party imports
import pytest
from tld import get_fld

# Local package imports
from final_page import final_page_entry
from first_party_responses import (
    CrawlDataError,
    first_party_responses,
    header_values,
    iter_crawl_hars,
)


def make_entry(
    url: str,
    status: int = 200,
    headers: tuple[tuple[str, str], ...] = (),
    redirect: str = "",
) -> dict:
    """HAR entry with fields Playwright records and analysis reads."""
    return {
        "request": {"url": url},
        "response": {
            "status": status,
            "redirectURL": redirect,
            "headers": [{"name": name, "value": value} for name, value in headers],
        },
    }


def make_har(*entries: dict) -> dict:
    return {"log": {"entries": list(entries)}}


def urls_of(entries) -> list[str]:
    return [entry["request"]["url"] for entry in entries]


def write_har(directory: Path, site: str, har: dict) -> None:
    # Text-mode write on Windows gives CRLF.
    with open(directory / f"{site}.har", "w", encoding="utf-8", newline="\n") as har_file:
        json.dump(har, har_file)


# *******************************************
# first_party_responses
# *******************************************


def test_subdomain_of_final_page_is_first_party() -> None:
    har = make_har(
        make_entry("https://www.ru.nl/"),
        make_entry("https://static.ru.nl/app.js"),
    )
    assert urls_of(first_party_responses(har, "ru.nl")) == [
        "https://www.ru.nl/",
        "https://static.ru.nl/app.js",
    ]


def test_redirect_moves_first_party_to_landing_domain() -> None:
    har = make_har(
        make_entry("https://glasgow.ac.uk/", status=301, redirect="https://www.gla.ac.uk/"),
        make_entry("https://www.gla.ac.uk/"),
        make_entry("https://cdn.gla.ac.uk/style.css"),
    )
    # Redirect must change eTLD+1 to exercise redirect rule.
    assert get_fld("glasgow.ac.uk", fix_protocol=True) != get_fld("www.gla.ac.uk", fix_protocol=True)

    assert urls_of(first_party_responses(har, "glasgow.ac.uk")) == [
        "https://www.gla.ac.uk/",
        "https://cdn.gla.ac.uk/style.css",
    ]


def test_three_hop_redirect_reaches_final_page() -> None:
    har = make_har(
        make_entry("https://a.edu/", status=301, redirect="https://b.edu/"),
        make_entry("https://b.edu/", status=302, redirect="https://www.c.edu/"),
        make_entry("https://www.c.edu/"),
        make_entry("https://img.c.edu/logo.png"),
    )
    assert urls_of(first_party_responses(har, "a.edu")) == [
        "https://www.c.edu/",
        "https://img.c.edu/logo.png",
    ]


def test_all_first_party_responses_returned_in_order() -> None:
    har = make_har(
        make_entry("https://www.ru.nl/"),
        make_entry("https://www.googletagmanager.com/gtm.js"),
        make_entry("https://static.ru.nl/a.js"),
        make_entry("https://www.ru.nl/b.css"),
        make_entry("https://connect.facebook.net/fbevents.js"),
        make_entry("https://api.ru.nl/c.json"),
    )
    assert urls_of(first_party_responses(har, "ru.nl")) == [
        "https://www.ru.nl/",
        "https://static.ru.nl/a.js",
        "https://www.ru.nl/b.css",
        "https://api.ru.nl/c.json",
    ]


def test_status_zero_response_is_excluded() -> None:
    har = make_har(
        make_entry("https://www.ru.nl/"),
        make_entry("https://static.ru.nl/blocked.js", status=0),
    )
    assert urls_of(first_party_responses(har, "ru.nl")) == ["https://www.ru.nl/"]


def test_404_response_is_kept() -> None:
    har = make_har(
        make_entry("https://www.ru.nl/"),
        make_entry("https://www.ru.nl/missing.js", status=404),
    )
    assert urls_of(first_party_responses(har, "ru.nl")) == [
        "https://www.ru.nl/",
        "https://www.ru.nl/missing.js",
    ]


def test_third_party_response_is_excluded() -> None:
    har = make_har(
        make_entry("https://www.ru.nl/"),
        make_entry("https://www.google-analytics.com/collect"),
    )
    assert urls_of(first_party_responses(har, "ru.nl")) == ["https://www.ru.nl/"]


def test_lookalike_host_is_not_first_party() -> None:
    har = make_har(
        make_entry("https://www.ru.nl/"),
        make_entry("https://ru.nl.evil.com/x.js"),
        make_entry("https://notru.nl/y.js"),
    )
    assert urls_of(first_party_responses(har, "ru.nl")) == ["https://www.ru.nl/"]


def test_ip_address_page_compares_exact_host() -> None:
    har = make_har(
        make_entry("http://127.0.0.1:8000/"),
        make_entry("http://127.0.0.1:8000/app.js"),
        make_entry("http://127.0.0.2/other.js"),
        make_entry("https://www.ru.nl/named.js"),
    )
    assert urls_of(first_party_responses(har, "127.0.0.1")) == [
        "http://127.0.0.1:8000/",
        "http://127.0.0.1:8000/app.js",
    ]


def test_url_without_host_is_skipped() -> None:
    har = make_har(
        make_entry("https://www.ru.nl/"),
        make_entry("data:image/png;base64,iVBORw0KGgo="),
    )
    assert urls_of(first_party_responses(har, "ru.nl")) == ["https://www.ru.nl/"]


def test_har_without_entries_yields_no_responses() -> None:
    assert list(first_party_responses(make_har(), "ru.nl")) == []


# *******************************************
# header_values
# *******************************************


def test_header_values_match_case_insensitively_in_order() -> None:
    entry = make_entry(
        "https://www.ru.nl/",
        headers=(
            ("Permissions-Policy", "camera=()"),
            ("content-type", "text/html"),
            ("permissions-policy", "usb=()"),
            ("PERMISSIONS-POLICY", "geolocation=(self)"),
        ),
    )
    assert header_values(entry, "Permissions-Policy") == ["camera=()", "usb=()", "geolocation=(self)"]


def test_header_values_absent_returns_empty_list() -> None:
    entry = make_entry("https://www.ru.nl/", headers=(("content-type", "text/html"),))
    assert header_values(entry, "content-type") == ["text/html"]
    assert header_values(entry, "permissions-policy") == []


# *******************************************
# final_page_entry
# *******************************************


def test_final_page_entry_follows_redirect() -> None:
    landing = make_entry("https://www.gla.ac.uk/")
    har = make_har(
        make_entry("https://glasgow.ac.uk/", status=301, redirect="https://www.gla.ac.uk/"),
        landing,
        make_entry("https://cdn.gla.ac.uk/style.css"),
    )
    assert final_page_entry(har) is landing


def test_final_page_entry_returns_first_request_for_url() -> None:
    page_load = make_entry("https://www.ru.nl/")
    refetch = make_entry("https://www.ru.nl/")
    har = make_har(page_load, make_entry("https://static.ru.nl/a.js"), refetch)
    assert final_page_entry(har) is page_load


def test_final_page_entry_is_none_for_empty_har() -> None:
    assert final_page_entry(make_har()) is None


def test_final_page_entry_is_none_when_redirect_target_never_requested() -> None:
    unfinished = make_har(
        make_entry("https://ru.nl/", status=301, redirect="https://www.ru.nl/"),
    )
    assert final_page_entry(unfinished) is None


# *******************************************
# iter_crawl_hars
# *******************************************


def test_iter_crawl_hars_yields_site_from_file_stem_sorted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for site in ("vu.nl", "ru.nl", "uva.nl"):
        write_har(tmp_path, site, make_har(make_entry(f"https://www.{site}/")))
    (tmp_path / "ru.nl_pre_consent.png").write_bytes(b"")

    # NTFS already lists files alphabetically. Tests sort by reversing the list.
    original_glob = Path.glob
    monkeypatch.setattr(
        Path,
        "glob",
        lambda path, pattern: reversed(sorted(original_glob(path, pattern))),
    )

    sites = [site for site, _ in iter_crawl_hars(tmp_path)]
    assert sites == ["ru.nl", "uva.nl", "vu.nl"]


def test_missing_crawl_folder_raises_crawl_data_error(tmp_path: Path) -> None:
    with pytest.raises(CrawlDataError, match="not found"):
        list(iter_crawl_hars(tmp_path / "crawl_data_mobile"))


def test_folder_without_hars_raises_crawl_data_error(tmp_path: Path) -> None:
    (tmp_path / "ru.nl.webm").write_bytes(b"")
    with pytest.raises(CrawlDataError, match="No .har files"):
        list(iter_crawl_hars(tmp_path))


def test_invalid_json_har_raises_with_file_name(tmp_path: Path) -> None:
    write_har(tmp_path, "ru.nl", make_har(make_entry("https://www.ru.nl/")))
    (tmp_path / "vu.nl.har").write_text("{ not json", encoding="utf-8", newline="\n")

    hars = iter_crawl_hars(tmp_path)
    assert next(hars)[0] == "ru.nl"
    with pytest.raises(CrawlDataError, match=r"vu\.nl\.har"):
        next(hars)


def test_non_utf8_har_raises_with_file_name(tmp_path: Path) -> None:
    write_har(tmp_path, "ru.nl", make_har(make_entry("https://www.ru.nl/")))
    (tmp_path / "vu.nl.har").write_bytes(b'{"log": "\xff\xfe"}')

    hars = iter_crawl_hars(tmp_path)
    assert next(hars)[0] == "ru.nl"
    with pytest.raises(CrawlDataError, match=r"vu\.nl\.har"):
        next(hars)
