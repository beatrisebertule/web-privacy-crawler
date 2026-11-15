"""
Analysis-Q10: five Permissions-Policy features disabled on most websites, mobile crawl.

Only first-party responses count. (First party is resulting page after redirects)
Feature counts as disabled if its allowlist is empty, `camera=()`.
Each website counts once per feature.
"""

# Standard library imports
import csv
import enum
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

# Third party imports
import http_sf

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
CRAWL_DIRECTORY = ROOT / "crawl_data_mobile"
RESULTS_DIRECTORY = ROOT / "results"
SITE_LIST_PATH = ROOT / "sites.csv"
CSV_NAME = "q10_permissions_policy_disabled_mobile.csv"
TOP_FEATURE_COUNT = 5

PERMISSIONS_POLICY_HEADER = "permissions-policy"
FEATURE_POLICY_HEADER = "feature-policy"


class MalformedPermissionsPolicy(ValueError):
    """Invalid Permissions-Policy syntax. Browsers ignore the whole header."""


@dataclass(frozen=True)
class PolicyFeatures:
    """
    Features named in Permissions-Policy for a single response.

    `disabled`: empty allowlist, `name=()`
    `named_not_disabled`: any other value, such as `(self)`, `*` or an origin list
    """

    disabled: frozenset[str]
    named_not_disabled: frozenset[str]


def parse_permissions_policy(header_values: list[str]) -> PolicyFeatures:
    """
    Split a response's Permissions-Policy into disabled and other features.

    example: ["camera=(), usb=(self)"] -> disabled {"camera"}, named_not_disabled {"usb"}

    :param header_values: every Permissions-Policy value on one response, in order
    :return: Disabled and named-not-disabled features, both empty if no header.
    :raises MalformedPermissionsPolicy: if header isn't a valid structured field dictionary
    """
    if not header_values:
        return PolicyFeatures(frozenset(), frozenset())

    # Repeated header lines join with a comma before parsing, as RFC 9651 says.
    joined_value = ", ".join(header_values)
    try:
        members = http_sf.parse(joined_value.encode("utf-8"), tltype="dictionary")
    except (http_sf.StructuredFieldError, UnicodeEncodeError) as parse_error:
        raise MalformedPermissionsPolicy(f"{joined_value!r}: {parse_error}") from parse_error

    disabled = set()
    named_not_disabled = set()
    for feature, (value, _parameters) in members.items():
        # Empty allowlist means no origin gets the feature. (Package returns it as an empty list)
        if isinstance(value, list) and not value:
            disabled.add(feature)
        else:
            named_not_disabled.add(feature)
    return PolicyFeatures(frozenset(disabled), frozenset(named_not_disabled))


# *******************************************
# Counting per website
# *******************************************


class TieBreakLevel(enum.Enum):
    """Tiebreaker for a given row."""

    FINAL_PAGE = "final page count"
    ALPHABETICAL = "feature name"


@dataclass
class SiteObservation:
    """
    Disabled features found on one website.

    `mixed`: disabled in one response, allowed in another
    `feature_policy_only`: `Feature-Policy` only, no `Permissions-Policy`
    """

    website: str
    disabled: set[str] = field(default_factory=set)
    disabled_on_final_page: set[str] = field(default_factory=set)
    mixed: set[str] = field(default_factory=set)
    skipped_headers: list[str] = field(default_factory=list)
    feature_policy_only: bool = False
    first_party_response_count: int = 0
    permissions_policy_response_count: int = 0


@dataclass(frozen=True)
class FeatureRank:
    feature: str
    websites: int
    websites_on_final_page: int


@dataclass(frozen=True)
class TieReport:
    """Tie at the five-row cutoff. (Used in the caption)"""

    website_count: int
    tied_total: int
    tied_shown: int
    separated_by: TieBreakLevel


def observe_site(website: str, har: dict) -> SiteObservation:
    """
    Find disabled features on one website.

    :param website: site list entry, such as "ru.nl"
    :param har: parsed HAR file
    :return: Disabled features with counts for the report.
    """
    observation = SiteObservation(website)
    final_page_response = final_page_entry(har)
    named_not_disabled = set()
    saw_permissions_policy = False
    saw_feature_policy = False

    for entry in first_party_responses(har, website):
        observation.first_party_response_count += 1
        policy_values = header_values(entry, PERMISSIONS_POLICY_HEADER)
        if not policy_values:
            if header_values(entry, FEATURE_POLICY_HEADER):
                saw_feature_policy = True
            continue

        saw_permissions_policy = True
        observation.permissions_policy_response_count += 1
        try:
            features = parse_permissions_policy(policy_values)
        except MalformedPermissionsPolicy as malformed:
            # Browsers drop the whole header. (None of its features count)
            observation.skipped_headers.append(str(malformed))
            continue

        observation.disabled |= features.disabled
        named_not_disabled |= features.named_not_disabled
        # Identity, not equality. (Two entries can hold the same contents)
        if entry is final_page_response:
            observation.disabled_on_final_page |= features.disabled

    # Overlap means two responses disagree.
    observation.mixed = observation.disabled & named_not_disabled
    observation.feature_policy_only = saw_feature_policy and not saw_permissions_policy
    return observation


# *******************************************
# Ranking
# *******************************************


def rank_features(observations: list[SiteObservation]) -> list[FeatureRank]:
    """
    Rank disabled features by website count.

    :param observations: one per website
    :return: Full ranking, not just top five.
    """
    websites = Counter(
        feature
        for site in observations
        for feature in site.disabled
    )
    on_final_page = Counter(
        feature
        for site in observations
        for feature in site.disabled_on_final_page
    )
    ranking = [
        FeatureRank(feature, count, on_final_page[feature])
        for feature, count in websites.items()
    ]
    return sorted(
        ranking,
        key=lambda rank: (-rank.websites, -rank.websites_on_final_page, rank.feature),
    )


def tie_at_cutoff(ranking: list[FeatureRank], limit: int = TOP_FEATURE_COUNT) -> TieReport | None:
    """
    Find the tie at the five-row cutoff, if any.

    example: 7 features at 4 websites, cutoff keeps 2 -> TieReport(4, 7, 2, ...)

    :param ranking: output of `rank_features`
    :param limit: rows kept
    :return: None if there's no tie at the cutoff.
    """
    if len(ranking) <= limit:
        return None
    last_kept = ranking[limit - 1]
    first_dropped = ranking[limit]
    if last_kept.websites != first_dropped.websites:
        return None

    tied_total = sum(1 for rank in ranking if rank.websites == last_kept.websites)
    tied_shown = sum(1 for rank in ranking[:limit] if rank.websites == last_kept.websites)
    if last_kept.websites_on_final_page != first_dropped.websites_on_final_page:
        separated_by = TieBreakLevel.FINAL_PAGE
    else:
        separated_by = TieBreakLevel.ALPHABETICAL
    return TieReport(last_kept.websites, tied_total, tied_shown, separated_by)


# *******************************************
# Output
# *******************************************


def write_ranking_csv(ranking: list[FeatureRank], csv_path: Path) -> None:
    """
    Write the full ranking to CSV.

    :param ranking: output of `rank_features`
    :param csv_path: file to write (creates folder if missing)
    """
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with open(csv_path, "w", newline="", encoding="utf-8") as csv_file:
        # Default terminator is "\r\n" on every OS.
        writer = csv.writer(csv_file, lineterminator="\n")
        writer.writerow(["rank", "feature", "websites", "websites_on_final_page"])
        for position, rank in enumerate(ranking, start=1):
            writer.writerow([position, rank.feature, rank.websites, rank.websites_on_final_page])


def print_report(
    observations: list[SiteObservation],
    ranking: list[FeatureRank],
    site_list: frozenset[str],
    csv_path: Path,
) -> None:
    """
    Print the top five and caption details.

    Every section prints, with "none" if empty. (A missing line would look like a clean result)

    :param observations: one per website
    :param ranking: output of `rank_features`
    :param site_list: domains from `sites.csv`
    :param csv_path: where the full ranking went
    """
    first_party_total = sum(site.first_party_response_count for site in observations)
    policy_total = sum(site.permissions_policy_response_count for site in observations)
    print("Q10: Permissions-Policy features disabled, mobile crawl")
    print(
        f"Examined: {counted(len(observations), 'website')}, "
        f"{counted(first_party_total, 'first-party response')}, "
        f"{policy_total} with Permissions-Policy"
    )
    crawled = {site.website for site in observations}
    missing = sorted(site_list - crawled)
    not_listed = sorted(crawled - site_list)
    if missing:
        print(f"WARNING: missing from crawl: {', '.join(missing)}")
    if not_listed:
        print(f"WARNING: not on site list, still counted: {', '.join(not_listed)}")

    print()
    top = ranking[:TOP_FEATURE_COUNT]
    if len(top) < TOP_FEATURE_COUNT:
        print(f"Only {counted(len(top), 'feature')} disabled on any website")
    print(f"{'rank':<6}{'feature':<32}{'websites':>10}{'on final page':>16}")
    for position, rank in enumerate(top, start=1):
        print(f"{position:<6}{rank.feature:<32}{rank.websites:>10}{rank.websites_on_final_page:>16}")

    print()
    tie = tie_at_cutoff(ranking)
    if tie is None:
        print("Tie at cutoff: none")
    else:
        print(
            f"Tie at cutoff: {counted(tie.tied_total, 'feature')} tied at "
            f"{counted(tie.website_count, 'website')}, "
            f"{tie.tied_shown} shown, separated by {tie.separated_by.value}"
        )

    skipped_sites = [site for site in observations if site.skipped_headers]
    print("Skipped malformed headers:" + ("" if skipped_sites else " none"))
    for site in skipped_sites:
        for header_error in site.skipped_headers:
            print(f"  {site.website}: {header_error}")

    mixed_by_feature: dict[str, list[str]] = {}
    for site in observations:
        for feature in sorted(site.mixed):
            mixed_by_feature.setdefault(feature, []).append(site.website)
    print("Mixed websites:" + ("" if mixed_by_feature else " none"))
    for feature in sorted(mixed_by_feature):
        print(f"  {feature}: {', '.join(mixed_by_feature[feature])}")

    feature_policy_only = [site.website for site in observations if site.feature_policy_only]
    print(f"Feature-Policy only: {', '.join(feature_policy_only) or 'none'}")
    no_first_party = [site.website for site in observations if site.first_party_response_count == 0]
    print(f"No first-party responses: {', '.join(no_first_party) or 'none'}")
    print(f"CSV: {csv_path}")


# *******************************************
# Entry point
# *******************************************


def run(crawl_directory: Path, results_directory: Path, site_list: frozenset[str]) -> int:
    """
    Run Q10 on one crawl folder.

    :param crawl_directory: folder of `.har` files
    :param results_directory: where the CSV goes
    :param site_list: domains the crawl should hold, a mismatch prints a warning
    :return: 0 on success, 1 if crawl data can't be analyzed. (No CSV is written then)
    """
    observations = []
    try:
        for website, har in iter_crawl_hars(crawl_directory):
            try:
                observations.append(observe_site(website, har))
            except (KeyError, TypeError, AttributeError) as shape_error:
                # Bugs in this script raise these too. (Message says so)
                raise CrawlDataError(
                    f"{website}.har has an unexpected shape, or this script has a bug "
                    f"({type(shape_error).__name__}: {shape_error})"
                ) from shape_error
    except CrawlDataError as data_error:
        print(f"Q10 stopped: {data_error}", file=sys.stderr)
        return 1

    ranking = rank_features(observations)
    csv_path = results_directory / CSV_NAME
    write_ranking_csv(ranking, csv_path)
    print_report(observations, ranking, site_list, csv_path)
    return 0


def main() -> None:
    # Piped stdout on Windows defaults to cp1252.
    sys.stdout.reconfigure(encoding="utf-8")
    site_list = frozenset(
        domain for domain, _country
        in read_site_list(SITE_LIST_PATH)
    )
    sys.exit(run(CRAWL_DIRECTORY, RESULTS_DIRECTORY, site_list))


if __name__ == "__main__":
    main()
