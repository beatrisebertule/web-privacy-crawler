"""
Resume list. A crashed crawl must not re-crawl finished sites, and each mode keeps its own list.

Everything here is plain file logic. No browser needed.
"""

# Standard library imports
from pathlib import Path

# Local package imports
from crawler import (
    CrawlMode,
    add_to_crawled_list,
    read_crawled_list,
    read_site_list,
    select_sites_to_crawl,
)

SITES = [("ru.nl", "nl"), ("cam.ac.uk", "uk"), ("mit.edu", "us")]


def test_missing_list_means_nothing_crawled(tmp_path: Path) -> None:
    assert read_crawled_list(tmp_path / "absent.txt") == set()


def test_add_then_read_roundtrip(tmp_path: Path) -> None:
    crawled_list_path = tmp_path / "crawled.txt"

    add_to_crawled_list(crawled_list_path, "ru.nl", "nl")
    add_to_crawled_list(crawled_list_path, "cam.ac.uk", "UK")

    assert read_crawled_list(crawled_list_path) == {("ru.nl", "nl"), ("cam.ac.uk", "uk")}


def test_select_skips_finished_sites_and_keeps_order(tmp_path: Path) -> None:
    crawled_list_path = tmp_path / "crawled.txt"
    add_to_crawled_list(crawled_list_path, "cam.ac.uk", "uk")

    assert select_sites_to_crawl(SITES, crawled_list_path) == [("ru.nl", "nl"), ("mit.edu", "us")]


def test_each_mode_has_its_own_resume_file() -> None:
    resume_paths = {mode.crawled_list_path for mode in CrawlMode}

    assert len(resume_paths) == len(CrawlMode)
    assert all(mode.value in mode.crawled_list_path.name for mode in CrawlMode)


def test_each_mode_has_its_own_output_directory() -> None:
    assert {mode.output_directory.name for mode in CrawlMode} == {
        "crawl_data_desktop",
        "crawl_data_mobile",
        "crawl_data_block",
        "crawl_data_ignore",
    }


def test_site_list_skips_header_and_blank_rows(tmp_path: Path) -> None:
    site_list_path = tmp_path / "sites.csv"
    site_list_path.write_text(
        "domain,country,university\nru.nl,NL,Radboud\n\n,,\nmit.edu,us,MIT\n", encoding="utf-8"
    )

    assert read_site_list(site_list_path) == [("ru.nl", "nl"), ("mit.edu", "us")]


def test_site_list_strips_spaces_around_values(tmp_path: Path) -> None:
    site_list_path = tmp_path / "sites.csv"
    site_list_path.write_text("domain,country,university\n vu.nl , nl ,VU\n", encoding="utf-8")

    assert read_site_list(site_list_path) == [("vu.nl", "nl")]


def test_site_list_with_only_header_is_empty(tmp_path: Path) -> None:
    site_list_path = tmp_path / "sites.csv"
    site_list_path.write_text("domain,country,university\n", encoding="utf-8")

    assert read_site_list(site_list_path) == []


def test_repo_site_list_has_thirty_sites_ten_per_country() -> None:
    sites = read_site_list(Path(__file__).resolve().parent.parent / "sites.csv")

    assert len(sites) == 30
    assert sorted(set(country for _, country in sites)) == ["nl", "uk", "us"]
    assert all(sum(1 for _, country in sites if country == wanted) == 10 for wanted in ("nl", "uk", "us"))
