"""
Analysis-Q11: websites where a first-party response sets Referrer-Policy `no-referrer`, desktop crawl.

Only first-party responses count (first party is resulting page after redirects).
Website counts if a response's effective policy is `no-referrer`.
Effective policy is the last one the browser recognizes. `no-referrer, origin` means `origin`.
"""

# Standard library imports
import csv
import enum
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Local package imports
from final_page import final_page_entry
from first_party_responses import (
    CrawlDataError,
    first_party_responses,
    header_values,
    iter_crawl_hars,
)
from report_text import counted

# crawler_src is not a package. Path entry instead of an install.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "crawler_src"))
from crawler import read_site_list  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CRAWL_DIRECTORY = ROOT / "crawl_data_desktop"
RESULTS_DIRECTORY = ROOT / "results"
SITE_LIST_PATH = ROOT / "crawler_src" / "sites.csv"
CSV_NAME = "q11_referrer_policy_no_referrer_desktop.csv"
# First two are the assignment's column names for the Q11 table.
CSV_COLUMNS = [
    "Website",
    "Country",
    "No-referrer",
    "No-referrer on final page",
    "Effective policies",
    "No-referrer overridden",
]

REFERRER_POLICY_HEADER = "referrer-policy"
# Same word the assignment uses for a missing value.
COUNTRY_NOT_LISTED = "na"


class ReferrerPolicy(enum.Enum):
    """Referrer-Policy values a browser recognizes."""

    NO_REFERRER = "no-referrer"
    NO_REFERRER_WHEN_DOWNGRADE = "no-referrer-when-downgrade"
    ORIGIN = "origin"
    ORIGIN_WHEN_CROSS_ORIGIN = "origin-when-cross-origin"
    SAME_ORIGIN = "same-origin"
    STRICT_ORIGIN = "strict-origin"
    STRICT_ORIGIN_WHEN_CROSS_ORIGIN = "strict-origin-when-cross-origin"
    UNSAFE_URL = "unsafe-url"


_POLICY_BY_TOKEN = {policy.value: policy for policy in ReferrerPolicy}


@dataclass(frozen=True)
class ReferrerPolicyHeader:
    """
    Referrer-Policy of a single response.

    `effective`: last recognized token, None if none
    `listed`: every recognized token
    """

    effective: ReferrerPolicy | None
    listed: frozenset[ReferrerPolicy]


def parse_referrer_policy(header_values: list[str]) -> ReferrerPolicyHeader:
    """
    Find the policy a response's Referrer-Policy sets.

    Unknown and empty tokens are skipped. Chromium ignores case.

    example: ["no-referrer, strict-origin-when-cross-origin"] -> effective strict-origin-when-cross-origin

    :param header_values: every Referrer-Policy value on one response, in order
    :return: Effective and listed policies. With no header, effective is None and listed is empty.
    """
    # Repeated header lines read the same as one comma-separated line.
    tokens = (
        token.strip(" \t").lower()
        for token in ",".join(header_values).split(",")
    )
    recognized = [_POLICY_BY_TOKEN[token] for token in tokens if token in _POLICY_BY_TOKEN]
    return ReferrerPolicyHeader(
        effective=recognized[-1] if recognized else None,
        listed=frozenset(recognized),
    )


# *******************************************
# Counting per website
# *******************************************


@dataclass
class SiteObservation:
    """
    Referrer-Policy found on one website.

    `no_referrer_listed`: `no-referrer` named in a header even if it wasn't effective
    `unrecognized_headers`: raw values with no policy the browser knows
    """

    website: str
    country: str
    no_referrer: bool = False
    no_referrer_on_final_page: bool = False
    no_referrer_listed: bool = False
    effective_policies: set[ReferrerPolicy] = field(default_factory=set)
    unrecognized_headers: list[str] = field(default_factory=list)
    first_party_response_count: int = 0
    referrer_policy_response_count: int = 0

    @property
    def no_referrer_overridden(self) -> bool:
        """`no-referrer` named somewhere but never the effective policy."""
        return self.no_referrer_listed and not self.no_referrer


def observe_site(website: str, country: str, har: dict) -> SiteObservation:
    """
    Find Referrer-Policy on one website's first-party responses.

    :param website: site list entry, such as "ru.nl"
    :param country: from the site list, such as "nl"
    :param har: parsed HAR file
    :return: Policies found with counts for the report.
    """
    observation = SiteObservation(website, country)
    final_page_response = final_page_entry(har)

    for entry in first_party_responses(har, website):
        observation.first_party_response_count += 1
        policy_values = header_values(entry, REFERRER_POLICY_HEADER)
        if not policy_values:
            continue

        observation.referrer_policy_response_count += 1
        header = parse_referrer_policy(policy_values)
        if ReferrerPolicy.NO_REFERRER in header.listed:
            observation.no_referrer_listed = True
        if header.effective is None:
            observation.unrecognized_headers.append(", ".join(policy_values))
            continue

        observation.effective_policies.add(header.effective)
        if header.effective is ReferrerPolicy.NO_REFERRER:
            observation.no_referrer = True
            # Identity, not equality (two entries can hold the same contents).
            if entry is final_page_response:
                observation.no_referrer_on_final_page = True

    return observation


# *******************************************
# Output
# *******************************************


def yes_no(value: bool) -> str:
    return "yes" if value else "no"


def write_observations_csv(observations: list[SiteObservation], csv_path: Path) -> None:
    """
    Write one row per website to CSV.

    :param observations: one per website
    :param csv_path: file to write (creates folder if missing)
    """
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with open(csv_path, "w", newline="", encoding="utf-8") as csv_file:
        # Default terminator is "\r\n" on every OS.
        writer = csv.writer(csv_file, lineterminator="\n")
        writer.writerow(CSV_COLUMNS)
        for site in sorted(observations, key=lambda site: site.website):
            writer.writerow([
                site.website,
                site.country,
                yes_no(site.no_referrer),
                yes_no(site.no_referrer_on_final_page),
                " ".join(sorted(policy.value for policy in site.effective_policies)),
                yes_no(site.no_referrer_overridden),
            ])


def print_report(observations: list[SiteObservation], site_list: frozenset[str], csv_path: Path) -> None:
    """
    Print the no-referrer table and caption details.

    Every section prints "none" if empty, since a missing line would look like a clean result.

    :param observations: one per website
    :param site_list: domains from `sites.csv`
    :param csv_path: where the CSV went
    """
    by_website = sorted(observations, key=lambda site: site.website)
    first_party_total = sum(site.first_party_response_count for site in observations)
    policy_total = sum(site.referrer_policy_response_count for site in observations)
    print("Q11: websites with a first-party Referrer-Policy of no-referrer, desktop crawl")
    print(
        f"Examined: {counted(len(observations), 'website')}, "
        f"{counted(first_party_total, 'first-party response')}, "
        f"{policy_total} with Referrer-Policy"
    )
    crawled = {site.website for site in observations}
    missing = sorted(site_list - crawled)
    not_listed = sorted(crawled - site_list)
    if missing:
        print(f"WARNING: missing from crawl: {', '.join(missing)}")
    if not_listed:
        print(f"WARNING: not on site list, still counted: {', '.join(not_listed)}")

    print()
    no_referrer_sites = [site for site in by_website if site.no_referrer]
    if no_referrer_sites:
        print(f"{'website':<28}{'country':<10}on final page")
        for site in no_referrer_sites:
            print(f"{site.website:<28}{site.country.upper():<10}{yes_no(site.no_referrer_on_final_page)}")
    else:
        print("No website set no-referrer")
    print(f"Counted: {counted(len(no_referrer_sites), 'website')}")

    print()
    overridden = [site.website for site in by_website if site.no_referrer_overridden]
    print(f"no-referrer listed but overridden: {', '.join(overridden) or 'none'}")
    unrecognized_sites = [site for site in by_website if site.unrecognized_headers]
    print("Headers with no known policy:" + ("" if unrecognized_sites else " none"))
    for site in unrecognized_sites:
        for header_value in site.unrecognized_headers:
            print(f"  {site.website}: {header_value!r}")
    no_first_party = [site.website for site in by_website if site.first_party_response_count == 0]
    print(f"No first-party responses: {', '.join(no_first_party) or 'none'}")
    print(f"CSV: {csv_path}")


# *******************************************
# Entry point
# *******************************************


def run(crawl_directory: Path, results_directory: Path, site_countries: dict[str, str]) -> int:
    """
    Run Q11 on one crawl folder.

    :param crawl_directory: folder of `.har` files
    :param results_directory: where the CSV goes
    :param site_countries: country for each site list domain
    :return: 0 on success, 1 if crawl data can't be analyzed and no CSV is written
    """
    observations = []
    try:
        for website, har in iter_crawl_hars(crawl_directory):
            country = site_countries.get(website, COUNTRY_NOT_LISTED)
            try:
                observations.append(observe_site(website, country, har))
            except (KeyError, TypeError, AttributeError) as shape_error:
                # Bugs in this script raise these too (message says so).
                raise CrawlDataError(
                    f"{website}.har has an unexpected shape, or this script has a bug "
                    f"({type(shape_error).__name__}: {shape_error})"
                ) from shape_error
    except CrawlDataError as data_error:
        print(f"Q11 stopped: {data_error}", file=sys.stderr)
        return 1

    csv_path = results_directory / CSV_NAME
    write_observations_csv(observations, csv_path)
    print_report(observations, frozenset(site_countries), csv_path)
    return 0


def main() -> None:
    # Piped stdout on Windows defaults to cp1252.
    sys.stdout.reconfigure(encoding="utf-8")
    site_countries = dict(read_site_list(SITE_LIST_PATH))
    sys.exit(run(CRAWL_DIRECTORY, RESULTS_DIRECTORY, site_countries))


if __name__ == "__main__":
    main()
