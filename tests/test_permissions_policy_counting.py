"""
Tests for Q10's counting per website, ranking, and output.

Exclusion tests all have at least one feature that does get counted
so we know it's not just discarding everything.
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
q10 = importlib.import_module("10_analysis")

FeatureRank = q10.FeatureRank
SiteObservation = q10.SiteObservation
TieBreakLevel = q10.TieBreakLevel
TieReport = q10.TieReport

PERMISSIONS_POLICY = "Permissions-Policy"


def policy(value: str) -> tuple[tuple[str, str], ...]:
    return ((PERMISSIONS_POLICY, value),)


def observation(
    website: str,
    disabled: set[str],
    on_final_page: set[str] = frozenset(),
    first_party_responses: int = 1,
) -> SiteObservation:
    return SiteObservation(
        website,
        disabled=set(disabled),
        disabled_on_final_page=set(on_final_page),
        first_party_response_count=first_party_responses,
    )


# *******************************************
# observe_site
# *******************************************


def test_feature_counted_once_per_site_across_responses() -> None:
    har = make_har(
        make_entry("https://www.ru.nl/", headers=policy("camera=()")),
        make_entry("https://static.ru.nl/a.js", headers=policy("camera=()")),
        make_entry("https://www.ru.nl/b.css", headers=policy("camera=()")),
    )
    site = q10.observe_site("ru.nl", har)
    assert site.disabled == {"camera"}
    assert q10.rank_features([site]) == [FeatureRank("camera", 1, 1)]


def test_subresource_disable_counts_for_site_not_final_page() -> None:
    har = make_har(
        make_entry("https://www.ru.nl/", headers=policy("usb=()")),
        make_entry("https://static.ru.nl/a.js", headers=policy("camera=()")),
    )
    site = q10.observe_site("ru.nl", har)
    assert site.disabled == {"camera", "usb"}
    assert site.disabled_on_final_page == {"usb"}


def test_final_page_found_after_redirect() -> None:
    har = make_har(
        make_entry("https://glasgow.ac.uk/", status=301, redirect="https://www.gla.ac.uk/"),
        make_entry("https://www.gla.ac.uk/", headers=policy("camera=()")),
        make_entry("https://cdn.gla.ac.uk/a.js", headers=policy("usb=()")),
    )
    site = q10.observe_site("glasgow.ac.uk", har)
    assert site.disabled == {"camera", "usb"}
    assert site.disabled_on_final_page == {"camera"}


def test_third_party_disable_is_ignored() -> None:
    har = make_har(
        make_entry("https://www.ru.nl/", headers=policy("usb=()")),
        make_entry("https://www.googletagmanager.com/gtm.js", headers=policy("camera=()")),
    )
    assert q10.observe_site("ru.nl", har).disabled == {"usb"}


def test_unreceived_response_is_ignored() -> None:
    har = make_har(
        make_entry("https://www.ru.nl/", headers=policy("usb=()")),
        make_entry("https://static.ru.nl/a.js", status=0, headers=policy("camera=()")),
    )
    assert q10.observe_site("ru.nl", har).disabled == {"usb"}


def test_malformed_header_skipped_other_responses_still_count() -> None:
    har = make_har(
        make_entry("https://www.ru.nl/", headers=policy("camera=(), Usb=()")),
        make_entry("https://static.ru.nl/a.js", headers=policy("microphone=()")),
    )
    site = q10.observe_site("ru.nl", har)
    assert site.disabled == {"microphone"}
    assert len(site.skipped_headers) == 1
    assert "Usb" in site.skipped_headers[0]
    assert site.disabled_on_final_page == set()


def test_mixed_site_detected() -> None:
    har = make_har(
        make_entry("https://www.ru.nl/", headers=policy("camera=(), usb=()")),
        make_entry("https://static.ru.nl/a.js", headers=policy("camera=(self)")),
    )
    site = q10.observe_site("ru.nl", har)
    assert site.mixed == {"camera"}
    assert site.disabled == {"camera", "usb"}


def test_feature_policy_only_flag() -> None:
    only_old = make_har(make_entry("https://www.ru.nl/", headers=(("Feature-Policy", "camera 'none'"),)))
    both = make_har(
        make_entry("https://www.vu.nl/", headers=(("Feature-Policy", "camera 'none'"),)),
        make_entry("https://static.vu.nl/a.js", headers=policy("usb=()")),
    )
    assert q10.observe_site("ru.nl", only_old).feature_policy_only is True
    both_site = q10.observe_site("vu.nl", both)
    assert both_site.feature_policy_only is False
    assert both_site.disabled == {"usb"}


# *******************************************
# Ranking
# *******************************************


def test_ranking_order_uses_all_three_keys() -> None:
    # Websites puts e first, final page puts b over a and g over f, name puts c over d.
    observations = [
        observation("s1.nl", {"e", "a", "b", "c"}, {"b"}),
        observation("s2.nl", {"e", "a", "b", "d"}, {"b", "a"}),
        observation("s3.nl", {"e", "a", "b", "c", "d"}),
        observation("s4.nl", {"e", "f", "g"}, {"g"}),
        observation("s5.nl", set()),
        observation("s6.nl", set()),
    ]
    assert q10.rank_features(observations) == [
        FeatureRank("e", 4, 0),
        FeatureRank("b", 3, 2),
        FeatureRank("a", 3, 1),
        FeatureRank("c", 2, 0),
        FeatureRank("d", 2, 0),
        FeatureRank("g", 1, 1),
        FeatureRank("f", 1, 0),
    ]


def test_tie_split_by_final_page() -> None:
    ranking = [
        FeatureRank("a", 2, 2),
        FeatureRank("b", 2, 2),
        FeatureRank("c", 2, 1),
        FeatureRank("d", 2, 1),
        FeatureRank("e", 2, 1),
        FeatureRank("f", 2, 0),
    ]
    assert q10.tie_at_cutoff(ranking) == TieReport(2, 6, 5, TieBreakLevel.FINAL_PAGE)


def test_tie_split_alphabetically() -> None:
    ranking = [
        FeatureRank("x", 3, 0),
        FeatureRank("a", 2, 0),
        FeatureRank("b", 2, 0),
        FeatureRank("c", 2, 0),
        FeatureRank("d", 2, 0),
        FeatureRank("e", 2, 0),
        FeatureRank("f", 2, 0),
    ]
    assert q10.tie_at_cutoff(ranking) == TieReport(2, 6, 4, TieBreakLevel.ALPHABETICAL)


def test_no_tie_report_when_fifth_and_sixth_differ() -> None:
    ranking = [FeatureRank(name, 3, 0) for name in "abcde"] + [FeatureRank("f", 2, 0)]
    assert q10.tie_at_cutoff(ranking) is None
    tied = [FeatureRank(name, 3, 0) for name in "abcdef"]
    assert q10.tie_at_cutoff(tied) is not None


def test_no_tie_report_with_five_or_fewer_features() -> None:
    assert q10.tie_at_cutoff([FeatureRank(name, 1, 0) for name in "abcde"]) is None


# *******************************************
# Output
# *******************************************


def test_csv_has_lf_line_endings_and_full_ranking(tmp_path: Path) -> None:
    ranking = [FeatureRank(name, 7 - index, 0) for index, name in enumerate("abcdefg")]
    csv_path = tmp_path / "results" / "q10.csv"
    q10.write_ranking_csv(ranking, csv_path)

    # Read bytes, since text mode turns "\r\n" into "\n" and hides it.
    data = csv_path.read_bytes()
    assert b"\r" not in data
    assert data.decode("utf-8").splitlines() == [
        "Rank,Permission name,Number of distinct websites where this permission was disabled,Websites disabling it on the final page",
        "1,a,7,0",
        "2,b,6,0",
        "3,c,5,0",
        "4,d,4,0",
        "5,e,3,0",
        "6,f,2,0",
        "7,g,1,0",
    ]


def test_fewer_than_five_features(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    observations = [observation("ru.nl", {"a", "b", "c"})]
    ranking = q10.rank_features(observations)
    q10.print_report(observations, ranking, frozenset({"ru.nl"}), tmp_path / "q10.csv")
    output = capsys.readouterr().out
    assert "Only 3 features disabled on any website" in output
    assert "Tie at cutoff: none" in output


def test_counts_of_one_are_singular(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    observations = [observation("ru.nl", {"camera"})]
    q10.print_report(observations, q10.rank_features(observations), frozenset({"ru.nl"}), tmp_path / "q10.csv")
    output = capsys.readouterr().out
    assert "Examined: 1 website, 1 first-party response," in output
    assert "Only 1 feature disabled on any website" in output

    ranking = [FeatureRank(name, 1, 0) for name in "abcdef"]
    tied = [observation(f"s{index}.nl", {name}) for index, name in enumerate("abcdef")]
    q10.print_report(tied, ranking, frozenset(site.website for site in tied), tmp_path / "q10.csv")
    assert "Tie at cutoff: 6 features tied at 1 website, 5 shown" in capsys.readouterr().out


def test_zero_count_is_plural(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    observations = [observation("ru.nl", set())]
    q10.print_report(observations, q10.rank_features(observations), frozenset({"ru.nl"}), tmp_path / "q10.csv")
    assert "Only 0 features disabled on any website" in capsys.readouterr().out


def test_every_report_section_prints_when_empty(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    observations = [observation("ru.nl", {"camera"})]
    q10.print_report(observations, q10.rank_features(observations), frozenset({"ru.nl"}), tmp_path / "q10.csv")
    output = capsys.readouterr().out
    for line in [
        "Tie at cutoff: none",
        "Skipped malformed headers: none",
        "Mixed websites: none",
        "Feature-Policy only: none",
        "No first-party responses: none",
    ]:
        assert line in output
    assert "WARNING" not in output


def test_report_lists_sites_in_each_section(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    mixed = observation("ru.nl", {"camera"})
    mixed.mixed = {"camera"}
    mixed.skipped_headers = ["'Usb=()': bad key"]
    old_header = observation("vu.nl", set())
    old_header.feature_policy_only = True
    no_responses = observation("uu.nl", set(), first_party_responses=0)
    observations = [mixed, old_header, no_responses]

    site_list = frozenset({"ru.nl", "vu.nl", "uu.nl"})
    q10.print_report(observations, q10.rank_features(observations), site_list, tmp_path / "q10.csv")
    output = capsys.readouterr().out
    assert "  ru.nl: 'Usb=()': bad key" in output
    assert "  camera: ru.nl" in output
    assert "Feature-Policy only: vu.nl" in output
    assert "No first-party responses: uu.nl" in output


# *******************************************
# run, end to end
# *******************************************


def test_run_end_to_end_on_tmp_crawl(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    crawl = tmp_path / "crawl_data_mobile"
    crawl.mkdir()
    write_har(crawl, "ru.nl", make_har(make_entry("https://www.ru.nl/", headers=policy("camera=(), usb=()"))))
    write_har(
        crawl,
        "glasgow.ac.uk",
        make_har(
            make_entry("https://glasgow.ac.uk/", status=301, redirect="https://www.gla.ac.uk/"),
            make_entry("https://www.gla.ac.uk/", headers=policy("camera=()")),
        ),
    )
    write_har(crawl, "vu.nl", make_har(make_entry("https://www.vu.nl/")))

    assert q10.run(crawl, tmp_path / "results", frozenset({"ru.nl", "glasgow.ac.uk", "vu.nl", "uu.nl"})) == 0

    csv_lines = (tmp_path / "results" / q10.CSV_NAME).read_text(encoding="utf-8").splitlines()
    assert csv_lines == [
        "Rank,Permission name,Number of distinct websites where this permission was disabled,Websites disabling it on the final page",
        "1,camera,2,2",
        "2,usb,1,1",
    ]
    output = capsys.readouterr().out
    assert "Examined: 3 websites, 3 first-party responses, 2 with Permissions-Policy" in output
    assert "WARNING: missing from crawl: uu.nl" in output
    assert "not on site list" not in output


def test_run_warns_on_site_mismatch_with_equal_count(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    # vu.nl's HAR is missing, but a stray example.org.har makes the site counts equal.
    crawl = tmp_path / "crawl_data_mobile"
    crawl.mkdir()
    write_har(crawl, "ru.nl", make_har(make_entry("https://www.ru.nl/", headers=policy("camera=()"))))
    write_har(crawl, "example.org", make_har(make_entry("https://example.org/", headers=policy("usb=()"))))

    assert q10.run(crawl, tmp_path / "results", frozenset({"ru.nl", "vu.nl"})) == 0
    output = capsys.readouterr().out
    assert "WARNING: missing from crawl: vu.nl" in output
    assert "WARNING: not on site list, still counted: example.org" in output


def test_run_missing_folder_returns_1_and_writes_nothing(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    assert q10.run(tmp_path / "crawl_data_mobile", tmp_path / "results", frozenset({"ru.nl"})) == 1
    assert not (tmp_path / "results").exists()
    assert "Crawl folder not found" in capsys.readouterr().err


def headers_as_object(entry: dict) -> None:
    entry["response"]["headers"] = {"Permissions-Policy": "camera=()"}


def header_name_as_number(entry: dict) -> None:
    entry["response"]["headers"] = [{"name": 5, "value": "camera=()"}]


def status_missing(entry: dict) -> None:
    del entry["response"]["status"]


@pytest.mark.parametrize(
    "break_entry",
    [
        pytest.param(headers_as_object, id="TypeError"),
        pytest.param(header_name_as_number, id="AttributeError"),
        pytest.param(status_missing, id="KeyError"),
    ],
)
def test_run_wrong_type_field_names_site(
    break_entry,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    crawl = tmp_path / "crawl_data_mobile"
    crawl.mkdir()
    write_har(crawl, "ru.nl", make_har(make_entry("https://www.ru.nl/", headers=policy("camera=()"))))
    broken_entry = make_entry("https://www.vu.nl/")
    break_entry(broken_entry)
    write_har(crawl, "vu.nl", make_har(broken_entry))

    assert q10.run(crawl, tmp_path / "results", frozenset({"ru.nl", "vu.nl"})) == 1
    assert not (tmp_path / "results").exists()
    assert "vu.nl.har has an unexpected shape" in capsys.readouterr().err


def test_run_invalid_json_returns_1(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    crawl = tmp_path / "crawl_data_mobile"
    crawl.mkdir()
    write_har(crawl, "ru.nl", make_har(make_entry("https://www.ru.nl/", headers=policy("camera=()"))))
    (crawl / "vu.nl.har").write_text("{ not json", encoding="utf-8", newline="\n")

    assert q10.run(crawl, tmp_path / "results", frozenset({"ru.nl", "vu.nl"})) == 1
    assert not (tmp_path / "results").exists()
    assert "vu.nl.har" in capsys.readouterr().err


# *******************************************
# main
# *******************************************


def point_main_at(monkeypatch: pytest.MonkeyPatch, crawl: Path, results: Path, site_list: Path) -> None:
    monkeypatch.setattr(q10, "CRAWL_DIRECTORY", crawl)
    monkeypatch.setattr(q10, "RESULTS_DIRECTORY", results)
    monkeypatch.setattr(q10, "SITE_LIST_PATH", site_list)


def test_main_runs_on_its_folders_and_exits_with_run_code(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    crawl = tmp_path / "crawl_data_mobile"
    crawl.mkdir()
    write_har(crawl, "ru.nl", make_har(make_entry("https://www.ru.nl/", headers=policy("camera=()"))))
    site_list = tmp_path / "sites.csv"
    site_list.write_text("domain,country,university\nru.nl,nl,Radboud\n", encoding="utf-8")
    point_main_at(monkeypatch, crawl, tmp_path / "results", site_list)

    with pytest.raises(SystemExit) as exit_info:
        q10.main()
    assert exit_info.value.code == 0
    assert (tmp_path / "results" / q10.CSV_NAME).read_text(encoding="utf-8").splitlines()[1] == "1,camera,1,1"
    assert "WARNING" not in capsys.readouterr().out


def test_main_prints_non_ascii_header_with_stdout_piped(tmp_path: Path) -> None:
    crawl = tmp_path / "crawl_data_mobile"
    crawl.mkdir()
    write_har(crawl, "ru.nl", make_har(make_entry("https://www.ru.nl/", headers=policy("相机=()"))))
    site_list = tmp_path / "sites.csv"
    site_list.write_bytes(b"domain,country,university\nru.nl,nl,Radboud\n")

    result = run_main_piped("10_analysis", crawl, tmp_path / "results", site_list)

    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    assert "相机=()" in result.stdout.decode("utf-8")


def test_main_exits_1_without_crawl_data(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    site_list = tmp_path / "sites.csv"
    site_list.write_text("domain,country,university\nru.nl,nl,Radboud\n", encoding="utf-8")
    point_main_at(monkeypatch, tmp_path / "crawl_data_mobile", tmp_path / "results", site_list)

    with pytest.raises(SystemExit) as exit_info:
        q10.main()
    assert exit_info.value.code == 1
    assert not (tmp_path / "results").exists()
    assert "crawl_data_mobile" in capsys.readouterr().err
