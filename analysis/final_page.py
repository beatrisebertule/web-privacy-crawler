"""
Page a visit ended up on, read from its HAR.

Assignment says third-partyness is judged against the page URL after redirects
(glasgow.ac.uk -> www.gla.ac.uk). HAR files are named after the site list entry, so the
file name is the wrong first party for a site that redirects to another domain.
"""

# Standard library imports
from urllib.parse import urljoin, urlsplit


def final_page_url(har: dict) -> str | None:
    """
    Follow the redirect chain from the first request in a HAR.

    example: glasgow.ac.uk HAR -> "https://www.gla.ac.uk/"

    :param har: parsed HAR file
    :return: URL of the last page in the chain, or None for a HAR with no entries.
    :rtype: str | None
    """
    entries = har.get("log", {}).get("entries", [])
    if not entries:
        return None

    # First entry per URL. A redirect target can be requested again later in the visit.
    entry_by_url = {}
    for entry in entries:
        entry_by_url.setdefault(entry["request"]["url"], entry)

    page_url = entries[0]["request"]["url"]
    visited_urls = set()
    while page_url not in visited_urls:
        visited_urls.add(page_url)
        entry = entry_by_url.get(page_url)
        redirect_target = entry["response"].get("redirectURL") if entry else None
        if not redirect_target:
            break
        # `redirectURL` can be relative to the URL that sent it.
        page_url = urljoin(page_url, redirect_target)
    return page_url


def final_page_host(har: dict, fallback: str) -> str:
    """
    Hostname of the page a visit ended up on.

    :param har: parsed HAR file
    :param fallback: returned when the HAR has no entries, usually the site list domain
    :return: Hostname such as "www.gla.ac.uk".
    :rtype: str
    """
    page_url = final_page_url(har)
    return (urlsplit(page_url).hostname if page_url else None) or fallback
