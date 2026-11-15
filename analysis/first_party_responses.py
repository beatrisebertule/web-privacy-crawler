"""
Received first-party responses from crawl HAR files.

Q10 and Q11 read headers from first-party responses only.

Received: HAR status above 0. Drops requests with no response, keeps 404s.
First party: same eTLD+1 as resulting page after redirects.
"""

# Standard library imports
import json
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import urlsplit

# Third party imports
from tld import get_fld

# Local package imports
from final_page import final_page_host


class CrawlDataError(Exception):
    """Crawl data unusable (missing folder, no HARs, broken HAR, etc.)"""


def iter_crawl_hars(crawl_directory: Path) -> Iterator[tuple[str, dict]]:
    """
    Find every HAR in crawl folder, sorted by file name.

    example: "ru.nl.har" -> ("ru.nl", <parsed HAR>)

    :param crawl_directory: crawler output folder, such as `crawl_data_mobile/`
    :return: (site from file name, parsed HAR) pairs
    :raises CrawlDataError: missing folder, no `.har` files, or unreadable HAR
    """
    if not crawl_directory.is_dir():
        raise CrawlDataError(f"Crawl folder not found: {crawl_directory}")
    har_paths = sorted(crawl_directory.glob("*.har"))
    if not har_paths:
        raise CrawlDataError(f"No .har files in {crawl_directory}")

    for har_path in har_paths:
        try:
            with open(har_path, encoding="utf-8") as har_file:
                har = json.load(har_file)
        except (json.JSONDecodeError, UnicodeDecodeError) as decode_error:
            raise CrawlDataError(f"{har_path.name} is not a readable HAR: {decode_error}") from decode_error
        yield har_path.stem, har


def is_received(entry: dict) -> bool:
    """
    Whether server answered request.

    :param entry: one HAR entry
    :return: True if status above 0, 404 included.
    """
    return entry["response"]["status"] > 0


def _registrable_domain(host: str) -> str | None:
    return get_fld(host, fix_protocol=True, fail_silently=True)


def _same_site(host: str, page_host: str, page_domain: str | None) -> bool:
    # IP addresses and `localhost` have no eTLD+1. (Only the exact host matches them)
    if page_domain is None:
        return host == page_host
    return _registrable_domain(host) == page_domain


def first_party_responses(har: dict, website: str) -> Iterator[dict]:
    """
    Find received first-party entries of one visit, in HAR order.

    :param har: parsed HAR file
    :param website: site list entry, first party if HAR has no entries
    :return: HAR entries
    """
    page_host = final_page_host(har, website)
    page_domain = _registrable_domain(page_host)
    for entry in har["log"]["entries"]:
        if not is_received(entry):
            continue
        host = urlsplit(entry["request"]["url"]).hostname
        if host and _same_site(host, page_host, page_domain):
            yield entry


def header_values(entry: dict, header_name: str) -> list[str]:
    """
    Values of one response header, in HAR order.

    A header sent twice shows up twice in the HAR.

    :param entry: one HAR entry
    :param header_name: header name, any case
    :return: Every value of header, or empty list if absent.
    """
    wanted_name = header_name.lower()
    return [
        header["value"] for header in entry["response"]["headers"]
        if header["name"].lower() == wanted_name
    ]
