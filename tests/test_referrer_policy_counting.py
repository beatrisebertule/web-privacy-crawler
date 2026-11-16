"""
Tests for Q11's counting per website and output.

Exclusion tests all have a first-party response that does get read.
"""

# Standard library imports
import importlib
from pathlib import Path

# Third party imports
import pytest

# Local package imports
from har_builders import make_entry, make_har, write_har
from piped_main import run_main_piped

# Import statement can't load a module name starting with a digit.
q11 = importlib.import_module("11_analysis")

ReferrerPolicy = q11.ReferrerPolicy
SiteObservation = q11.SiteObservation

NO_REFERRER = ReferrerPolicy.NO_REFERRER
ORIGIN = ReferrerPolicy.ORIGIN
STRICT_ORIGIN_WHEN_CROSS_ORIGIN = ReferrerPolicy.STRICT_ORIGIN_WHEN_CROSS_ORIGIN


def policy(value: str) -> tuple[tuple[str, str], ...]:
    return (("Referrer-Policy", value),)


def observe(website: str, *entries: dict) -> SiteObservation:
    return q11.observe_site(website, "nl", make_har(*entries))


def observation(website: str, country: str = "nl", **fields) -> SiteObservation:
    return SiteObservation(website, country, first_party_response_count=1, **fields)


# *******************************************
# observe_site
# *******************************************


def test_final_page_no_referrer_counts_on_final_page() -> None:
    site = observe("ru.nl", make_entry("https://www.ru.nl/", headers=policy("no-referrer")))
    assert site.no_referrer
    assert site.no_referrer_on_final_page


def test_stylesheet_no_referrer_counts_but_not_on_final_page() -> None:
    site = observe(
        "ru.nl",
        make_entry("https://www.ru.nl/"),
        make_entry("https://www.ru.nl/style.css", headers=policy("no-referrer")),
    )
    assert site.no_referrer
    assert not site.no_referrer_on_final_page


def test_redirect_to_other_domain_counts_under_site_list_name() -> None:
    site = observe(
        "glasgow.ac.uk",
        make_entry("https://glasgow.ac.uk/", status=301, redirect="https://www.gla.ac.uk/"),
        make_entry("https://www.gla.ac.uk/", headers=policy("no-referrer")),
    )
    assert site.website == "glasgow.ac.uk"
    assert site.no_referrer
    assert site.no_referrer_on_final_page


def test_first_party_redirect_response_counts() -> None:
    site = observe(
        "ru.nl",
        make_entry("https://ru.nl/", status=301, redirect="https://www.ru.nl/", headers=policy("no-referrer")),
        make_entry("https://www.ru.nl/", headers=policy("origin")),
    )
    assert site.no_referrer
    assert not site.no_referrer_on_final_page


def test_refetch_of_final_page_url_is_not_the_final_page() -> None:
    # Only the first request to the final URL loads the page.
    site = observe(
        "ru.nl",
        make_entry("https://www.ru.nl/", headers=policy("origin")),
        make_entry("https://www.ru.nl/", headers=policy("no-referrer")),
    )
    assert site.no_referrer
    assert not site.no_referrer_on_final_page


def test_404_response_counts() -> None:
    site = observe(
        "ru.nl",
        make_entry("https://www.ru.nl/"),
        make_entry("https://www.ru.nl/missing.css", status=404, headers=policy("no-referrer")),
    )
    assert site.no_referrer


def test_effective_policies_collects_every_policy() -> None:
    site = observe(
        "ru.nl",
        make_entry("https://www.ru.nl/", headers=policy("strict-origin-when-cross-origin")),
        make_entry("https://www.ru.nl/a.css", headers=policy("no-referrer")),
        make_entry("https://www.ru.nl/b.css", headers=policy("no-referrer")),
        make_entry("https://www.ru.nl/c.js", headers=policy("origin")),
    )
    assert site.effective_policies == {STRICT_ORIGIN_WHEN_CROSS_ORIGIN, NO_REFERRER, ORIGIN}
    assert site.referrer_policy_response_count == 4


def test_several_no_referrer_responses_count_once(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    site = observe(
        "ru.nl",
        make_entry("https://www.ru.nl/", headers=policy("no-referrer")),
        make_entry("https://www.ru.nl/a.css", headers=policy("no-referrer")),
        make_entry("https://www.ru.nl/b.css", headers=policy("no-referrer")),
    )
    q11.print_report([site], frozenset({"ru.nl"}), tmp_path / "q11.csv")
    assert "Counted: 1 website" in capsys.readouterr().out


def test_third_party_no_referrer_ignored() -> None:
    site = observe(
        "ru.nl",
        make_entry("https://www.ru.nl/", headers=policy("origin")),
        make_entry("https://cdn.example.com/x.js", headers=policy("no-referrer")),
    )
    assert not site.no_referrer
    assert site.effective_policies == {ORIGIN}


def test_unanswered_no_referrer_ignored() -> None:
    site = observe(
        "ru.nl",
        make_entry("https://www.ru.nl/", headers=policy("origin")),
        make_entry("https://www.ru.nl/blocked.js", status=0, headers=policy("no-referrer")),
    )
    assert not site.no_referrer
    assert site.effective_policies == {ORIGIN}


def test_overridden_no_referrer_listed_not_counted() -> None:
    site = observe(
        "ru.nl",
        make_entry("https://www.ru.nl/", headers=policy("no-referrer, strict-origin-when-cross-origin")),
    )
    assert not site.no_referrer
    assert site.no_referrer_overridden
    assert site.effective_policies == {STRICT_ORIGIN_WHEN_CROSS_ORIGIN}


def test_overridden_on_one_response_effective_on_another_is_not_overridden() -> None:
    site = observe(
        "ru.nl",
        make_entry("https://www.ru.nl/", headers=policy("no-referrer, origin")),
        make_entry("https://www.ru.nl/a.css", headers=policy("no-referrer")),
    )
    assert site.no_referrer
    assert not site.no_referrer_overridden


def test_header_with_no_known_policy_kept_raw() -> None:
    site = observe(
        "ru.nl",
        make_entry("https://www.ru.nl/", headers=policy("origin")),
        make_entry("https://www.ru.nl/a.css", headers=policy("made-up-policy")),
    )
    assert not site.no_referrer
    assert site.unrecognized_headers == ["made-up-policy"]
    assert site.effective_policies == {ORIGIN}


def test_har_with_no_entries_has_no_first_party_responses() -> None:
    site = observe("ru.nl")
    assert site.first_party_response_count == 0
    assert not site.no_referrer


# *******************************************
# Output
# *******************************************


def test_csv_one_sorted_row_per_site_with_lf(tmp_path: Path) -> None:
    observations = [
        observation("vu.nl", effective_policies={ORIGIN, STRICT_ORIGIN_WHEN_CROSS_ORIGIN}),
        observation("ru.nl", no_referrer=True, no_referrer_on_final_page=True, effective_policies={NO_REFERRER}),
        observation("cam.ac.uk", "uk", no_referrer_listed=True, effective_policies={ORIGIN}),
    ]
    csv_path = tmp_path / "results" / "q11.csv"
    q11.write_observations_csv(observations, csv_path)

    # Read bytes, since text mode turns "\r\n" into "\n" and hides it.
    assert csv_path.read_bytes() == (
        b"Website,Country,No-referrer,No-referrer on final page,Effective policies,No-referrer overridden\n"
        b"cam.ac.uk,uk,no,no,origin,yes\n"
        b"ru.nl,nl,yes,yes,no-referrer,no\n"
        b"vu.nl,nl,no,no,origin strict-origin-when-cross-origin,no\n"
    )


def test_report_table_sorted_with_uppercase_country(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    observations = [
        observation("vu.nl", no_referrer=True),
        observation("ru.nl", no_referrer=True, no_referrer_on_final_page=True),
        observation("cam.ac.uk", "uk", no_referrer=True),
        observation("uu.nl"),
    ]
    q11.print_report(observations, frozenset(site.website for site in observations), tmp_path / "q11.csv")
    lines = capsys.readouterr().out.splitlines()

    table = [line.split() for line in lines if line.split()[:1] in (["cam.ac.uk"], ["ru.nl"], ["vu.nl"], ["uu.nl"])]
    assert table == [["cam.ac.uk", "UK", "no"], ["ru.nl", "NL", "yes"], ["vu.nl", "NL", "no"]]
    assert "Counted: 3 websites" in lines


def test_report_sections_say_none_when_empty(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    q11.print_report([observation("ru.nl")], frozenset({"ru.nl"}), tmp_path / "q11.csv")
    output = capsys.readouterr().out
    for line in [
        "No website set no-referrer",
        "Counted: 0 websites",
        "no-referrer listed but overridden: none",
        "Headers with no known policy: none",
        "No first-party responses: none",
    ]:
        assert line in output
    assert "WARNING" not in output


def test_report_lists_overridden_unknown_and_empty_sites(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    observations = [
        observation("ru.nl", no_referrer=True),
        observation("vu.nl", no_referrer_listed=True),
        observation("uu.nl", unrecognized_headers=["made-up-policy"]),
        SiteObservation("uva.nl", "nl"),
    ]
    q11.print_report(observations, frozenset(site.website for site in observations), tmp_path / "q11.csv")
    output = capsys.readouterr().out
    assert "no-referrer listed but overridden: vu.nl" in output
    assert "  uu.nl: 'made-up-policy'" in output
    assert "No first-party responses: uva.nl" in output


def test_report_counts_of_one_are_singular(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    q11.print_report([observation("ru.nl", no_referrer=True)], frozenset({"ru.nl"}), tmp_path / "q11.csv")
    output = capsys.readouterr().out
    assert "Examined: 1 website, 1 first-party response," in output
    assert "Counted: 1 website" in output


def test_missing_and_stray_site_both_warned(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    # Same count on both sides, so only comparing names catches it.
    q11.print_report([observation("ru.nl"), observation("example.org")], frozenset({"ru.nl", "vu.nl"}), tmp_path / "q11.csv")
    output = capsys.readouterr().out
    assert "WARNING: missing from crawl: vu.nl" in output
    assert "WARNING: not on site list, still counted: example.org" in output


# *******************************************
# run, end to end
# *******************************************


def test_run_end_to_end_on_tmp_crawl(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    crawl = tmp_path / "crawl_data_desktop"
    crawl.mkdir()
    write_har(crawl, "ru.nl", make_har(make_entry("https://www.ru.nl/", headers=policy("no-referrer"))))
    write_har(crawl, "mit.edu", make_har(make_entry("https://www.mit.edu/", headers=policy("origin"))))
    write_har(crawl, "example.org", make_har(make_entry("https://example.org/", headers=policy("NO-REFERRER"))))

    exit_code = q11.run(crawl, tmp_path / "results", {"ru.nl": "nl", "mit.edu": "us"})

    assert exit_code == 0
    rows = (tmp_path / "results" / q11.CSV_NAME).read_text(encoding="utf-8").splitlines()
    assert rows[1:] == [
        "example.org,na,yes,yes,no-referrer,no",
        "mit.edu,us,no,no,origin,no",
        "ru.nl,nl,yes,yes,no-referrer,no",
    ]
    lines = capsys.readouterr().out.splitlines()
    assert "WARNING: not on site list, still counted: example.org" in lines
    assert any(line.split() == ["example.org", "NA", "yes"] for line in lines)
    assert "Counted: 2 websites" in lines


def test_run_stops_without_crawl_folder(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    assert q11.run(tmp_path / "crawl_data_desktop", tmp_path / "results", {}) == 1
    assert not (tmp_path / "results").exists()
    assert "crawl_data_desktop" in capsys.readouterr().err


def test_run_stops_on_empty_crawl_folder(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    crawl = tmp_path / "crawl_data_desktop"
    crawl.mkdir()
    assert q11.run(crawl, tmp_path / "results", {}) == 1
    assert not (tmp_path / "results").exists()
    assert "No .har files" in capsys.readouterr().err


def test_run_stops_on_unreadable_har(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    crawl = tmp_path / "crawl_data_desktop"
    crawl.mkdir()
    write_har(crawl, "ru.nl", make_har(make_entry("https://www.ru.nl/", headers=policy("no-referrer"))))
    (crawl / "vu.nl.har").write_bytes(b"{not json")
    assert q11.run(crawl, tmp_path / "results", {"ru.nl": "nl", "vu.nl": "nl"}) == 1
    assert not (tmp_path / "results").exists()
    assert "vu.nl.har" in capsys.readouterr().err


def test_run_stops_on_har_with_unexpected_shape(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    crawl = tmp_path / "crawl_data_desktop"
    crawl.mkdir()
    write_har(crawl, "ru.nl", {"log": {}})
    assert q11.run(crawl, tmp_path / "results", {"ru.nl": "nl"}) == 1
    assert not (tmp_path / "results").exists()
    assert "ru.nl.har has an unexpected shape" in capsys.readouterr().err


# *******************************************
# main
# *******************************************


def point_main_at(monkeypatch: pytest.MonkeyPatch, crawl: Path, results: Path, site_list: Path) -> None:
    monkeypatch.setattr(q11, "CRAWL_DIRECTORY", crawl)
    monkeypatch.setattr(q11, "RESULTS_DIRECTORY", results)
    monkeypatch.setattr(q11, "SITE_LIST_PATH", site_list)


def test_main_reads_country_from_site_list(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    crawl = tmp_path / "crawl_data_desktop"
    crawl.mkdir()
    write_har(crawl, "cam.ac.uk", make_har(make_entry("https://www.cam.ac.uk/", headers=policy("no-referrer"))))
    site_list = tmp_path / "sites.csv"
    site_list.write_bytes(b"domain,country,university\ncam.ac.uk,uk,Cambridge\n")
    point_main_at(monkeypatch, crawl, tmp_path / "results", site_list)

    with pytest.raises(SystemExit) as exit_info:
        q11.main()
    assert exit_info.value.code == 0
    rows = (tmp_path / "results" / q11.CSV_NAME).read_text(encoding="utf-8").splitlines()
    assert rows[1] == "cam.ac.uk,uk,yes,yes,no-referrer,no"
    output = capsys.readouterr().out
    assert "WARNING" not in output
    assert any(line.split() == ["cam.ac.uk", "UK", "yes"] for line in output.splitlines())


def test_main_prints_non_ascii_header_with_stdout_piped(tmp_path: Path) -> None:
    crawl = tmp_path / "crawl_data_desktop"
    crawl.mkdir()
    write_har(crawl, "ru.nl", make_har(make_entry("https://www.ru.nl/", headers=policy("政策"))))
    site_list = tmp_path / "sites.csv"
    site_list.write_bytes(b"domain,country,university\nru.nl,nl,Radboud\n")

    result = run_main_piped("11_analysis", crawl, tmp_path / "results", site_list)

    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    assert "ru.nl: '政策'" in result.stdout.decode("utf-8")


def test_main_exits_1_without_crawl_data(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    site_list = tmp_path / "sites.csv"
    site_list.write_bytes(b"domain,country,university\nru.nl,nl,Radboud\n")
    point_main_at(monkeypatch, tmp_path / "crawl_data_desktop", tmp_path / "results", site_list)

    with pytest.raises(SystemExit) as exit_info:
        q11.main()
    assert exit_info.value.code == 1
    assert not (tmp_path / "results").exists()
    assert "crawl_data_desktop" in capsys.readouterr().err
