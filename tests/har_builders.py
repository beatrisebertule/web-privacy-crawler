"""
Small HAR files built by hand for the analysis tests.

Fields match what Playwright records with `record_har_content="omit"` and the analysis reads.
"""

# Standard library imports
import json
from pathlib import Path


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


def write_har(directory: Path, site: str, har: dict) -> None:
    # Text-mode write on Windows gives CRLF.
    with open(directory / f"{site}.har", "w", encoding="utf-8", newline="\n") as har_file:
        json.dump(har, har_file)
