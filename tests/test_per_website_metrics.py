"""
Tests for how Q1, Q2 and Q4 share files in `results/`.

Q2 reads Q1's per-website CSV. Q4 writes one too, under its own name.
Most tests run the scripts as separate processes, mimics a real analysis run.
"""

# Standard library imports
import csv
import importlib
from pathlib import Path

# Third party imports
import pytest

# Local package imports
from har_builders import make_entry, make_har, write_har
from piped_main import run_script_piped

# Import statement can't load a module name starting with a digit.
q1 = importlib.import_module("01_analysis")
q2 = importlib.import_module("02_analysis")
q4 = importlib.import_module("04_analysis")

SCRIPTS = {"q1": "01_analysis.py", "q2": "02_analysis.py", "q4": "04_analysis.py"}
Q4_AFTER_Q1 = ("q1", "q4", "q2")

# Per-website CSV headers Q4 and Q1 write
Q4_COLUMNS = "country,website,requests,tp_requests,tp_domains,tp_entities"
Q1_COLUMNS = "crawl,website,requests,tp_requests,tp_domains,tp_entities"


# *******************************************
# Helpers
# *******************************************


def write_crawls(directory: Path) -> None:
    """
    Write `crawl_data_<mode>/` for every Q1 mode, and a small `entities.json`.

    Two sites in two countries. Desktop gets one extra third-party request, so crawls differ.
    """
    for mode in q1.MODES:
        crawl = directory / f"crawl_data_{mode}"
        crawl.mkdir()
        for site, page in (("ru.nl", "https://www.ru.nl/"), ("ox.ac.uk", "https://www.ox.ac.uk/")):
            entries = [
                make_entry(page),
                make_entry("https://www.googletagmanager.com/gtm.js"),
                make_entry("https://ads.example.com/pixel", status=0),
            ]
            if mode == "desktop" and site == "ru.nl":
                entries.append(make_entry("https://cdn.jsdelivr.net/npm/x.js"))
            write_har(crawl, site, make_har(*entries))
    write_lf(
        directory / "entities.json",
        '{"entities": {"Google": {"properties": ["google.com"], '
        '"resources": ["googletagmanager.com"]}}}',
    )


def write_lf(path: Path, text: str) -> None:
    # Text-mode write on Windows gives CRLF.
    with open(path, "w", encoding="utf-8", newline="\n") as text_file:
        text_file.write(text)


def run_q(question: str, directory: Path, arguments: list[str] | None = None):
    if arguments is None:
        arguments = [".", "entities.json"] if question in ("q1", "q4") else []
    return run_script_piped(SCRIPTS[question], arguments, directory)


def results_snapshot(directory: Path) -> dict[str, int]:
    results = directory / "results"
    if not results.is_dir():
        return {}
    return {
        path.relative_to(directory).as_posix(): path.stat().st_mtime_ns
        for path in results.rglob("*") if path.is_file()
    }


def assert_q2_stopped(process) -> str:
    """Q2 stopped through its own check, not through a crash. Returns stderr."""
    stderr = process.stderr.decode("cp1252")
    assert process.returncode == 1, stderr
    assert "Q2 stopped:" in stderr
    assert "Traceback" not in stderr
    return stderr


# *******************************************
# 01, then 04, then 02
# *******************************************


@pytest.fixture(scope="module")
def q4_after_q1_run(tmp_path_factory: pytest.TempPathFactory) -> dict:
    """
    One directory where 01, then 04, then 02 ran.

    `written` maps each question to the `results/` paths its run created or changed.
    """
    directory = tmp_path_factory.mktemp("q4_after_q1")
    write_crawls(directory)
    processes = {}
    written = {}
    for question in Q4_AFTER_Q1:
        before = results_snapshot(directory)
        processes[question] = run_q(question, directory)
        after = results_snapshot(directory)
        written[question] = {path for path, mtime in after.items() if before.get(path) != mtime}
    return {"directory": directory, "processes": processes, "written": written}


def test_q2_runs_after_q1_then_q4(q4_after_q1_run: dict) -> None:
    for question in Q4_AFTER_Q1:
        process = q4_after_q1_run["processes"][question]
        assert process.returncode == 0, process.stderr.decode("cp1252")
    table = (q4_after_q1_run["directory"] / "results" / "summary_table.csv").read_text("utf-8")
    labels = [line.split(",")[0] for line in table.splitlines()[1:]]
    assert labels == [label for _, label in q2.METRICS]


def test_q2_output_does_not_depend_on_order(q4_after_q1_run: dict, tmp_path: Path) -> None:
    write_crawls(tmp_path)
    for question in ("q4", "q1", "q2"):
        process = run_q(question, tmp_path)
        assert process.returncode == 0, process.stderr.decode("cp1252")
    for name in ("summary_table.csv", "summary_long.csv"):
        q4_after_q1 = (q4_after_q1_run["directory"] / "results" / name).read_bytes()
        assert (tmp_path / "results" / name).read_bytes() == q4_after_q1


def test_q1_q2_q4_write_no_file_in_common(q4_after_q1_run: dict) -> None:
    written = q4_after_q1_run["written"]
    assert f"results/{q1.METRICS_CSV}" in written["q1"]
    assert f"results/{q4.METRICS_CSV}" in written["q4"]
    assert written["q2"]
    assert not written["q1"] & written["q4"]
    assert not written["q1"] & written["q2"]
    assert not written["q2"] & written["q4"]


def test_q2_reads_the_file_q1_writes(q4_after_q1_run: dict) -> None:
    q2_input = Path(q2.IN_CSV).as_posix()
    assert q2_input in q4_after_q1_run["written"]["q1"]
    header = (q4_after_q1_run["directory"] / q2_input).read_text("utf-8").splitlines()[0]
    assert header.startswith("crawl,")


# *******************************************
# Q2 input check
# *******************************************


def test_q2_stops_when_input_is_missing(tmp_path: Path) -> None:
    stderr = assert_q2_stopped(run_q("q2", tmp_path))
    assert Path(q2.IN_CSV).name in stderr
    assert "01_analysis.py" in stderr
    assert not (tmp_path / "results").exists()


def test_q2_stops_on_q4_shaped_input(tmp_path: Path) -> None:
    # Same call twice, only the input's header differs
    for case in ("q1_shaped", "q4_shaped"):
        (tmp_path / case / "results").mkdir(parents=True)
    q1_rows = "".join(f"{mode},ru.nl,3,1,1,1\n" for mode in q2.MODES)
    write_lf(tmp_path / "q1_shaped" / "input.csv", f"{Q1_COLUMNS}\n{q1_rows}")
    write_lf(tmp_path / "q4_shaped" / "input.csv", f"{Q4_COLUMNS}\nnl,ru.nl,3,1,1,1\n")

    control = run_q("q2", tmp_path / "q1_shaped", ["input.csv"])
    assert control.returncode == 0, control.stderr.decode("cp1252")

    stderr = assert_q2_stopped(run_q("q2", tmp_path / "q4_shaped", ["input.csv"]))
    assert "input.csv is missing column crawl" in stderr
    assert "01_analysis.py" in stderr
    assert list((tmp_path / "q4_shaped" / "results").iterdir()) == []


def test_q2_ignores_stale_old_name(tmp_path: Path) -> None:
    # Leftover from older runs, under the name Q1 and Q4 once shared
    write_crawls(tmp_path)
    (tmp_path / "results").mkdir()
    write_lf(tmp_path / "results" / "per_website_metrics.csv", f"{Q4_COLUMNS}\nnl,ru.nl,3,1,1,1\n")

    assert_q2_stopped(run_q("q2", tmp_path))

    assert run_q("q1", tmp_path).returncode == 0
    after_q1 = run_q("q2", tmp_path)
    assert after_q1.returncode == 0, after_q1.stderr.decode("cp1252")


# *******************************************
# Q4 summary
# *******************************************


def q4_summary_rows(q4_after_q1_run: dict) -> list[list[str]]:
    summary = q4_after_q1_run["directory"] / "results" / q4.SUMMARY_CSV
    with open(summary, newline="", encoding="utf-8") as summary_file:
        return list(csv.reader(summary_file))


def test_q4_summary_header_names_each_value(q4_after_q1_run: dict) -> None:
    header, *rows = q4_summary_rows(q4_after_q1_run)
    assert header == ["country", "metric", "min", "median", "max"]
    assert rows
    for row in rows:
        assert len(row) == len(header)


def test_q4_summary_header_has_no_repeated_name(q4_after_q1_run: dict) -> None:
    header = q4_summary_rows(q4_after_q1_run)[0]
    assert len(set(header)) == len(header)


# *******************************************
# Q2 with a crawl that has no rows
# *******************************************


def run_q2_on_rows(directory: Path, modes: list[str]):
    """Q2 on a hand-written input with one row per given crawl."""
    (directory / "results").mkdir(parents=True)
    rows = "".join(f"{mode},ru.nl,3,1,1,1\n" for mode in modes)
    write_lf(directory / "input.csv", f"{Q1_COLUMNS}\n{rows}")
    return run_q("q2", directory, ["input.csv"])


def test_q2_marks_empty_crawl_with_dash(tmp_path: Path) -> None:
    process = run_q2_on_rows(tmp_path, [mode for mode in q2.MODES if mode != "ignore"])
    stderr = process.stderr.decode("cp1252")
    assert process.returncode == 0, stderr
    assert "Traceback" not in stderr
    assert "Q2 warning: no Ignore rows in input.csv" in stderr

    lines = (tmp_path / "results" / "summary_table.csv").read_text("utf-8").splitlines()
    header = lines[0].split(",")
    for line in lines[1:]:
        cells = dict(zip(header, line.split(",")))
        assert [cells[f"Ignore {stat}"] for stat in q2.STATS] == ["-", "-", "-"]
        assert cells["Desktop Median"].isdigit()

    ignore_header = (tmp_path / "results" / "summary_ignore.csv").read_text("utf-8").splitlines()[0]
    assert "n=0" in ignore_header


def test_q2_warns_only_for_empty_crawls(tmp_path: Path) -> None:
    process = run_q2_on_rows(tmp_path, q2.MODES)
    assert process.returncode == 0, process.stderr.decode("cp1252")
    assert "Q2 warning" not in process.stderr.decode("cp1252")


def test_q2_with_header_only_warns_for_every_crawl(tmp_path: Path) -> None:
    process = run_q2_on_rows(tmp_path, [])
    stderr = process.stderr.decode("cp1252")
    assert process.returncode == 0, stderr
    assert "Traceback" not in stderr
    assert stderr.count("Q2 warning") == len(q2.MODES)


def test_format_stat_formats_numbers_and_nan() -> None:
    assert q2.format_stat(3.0) == "3"
    assert q2.format_stat(2.5) == "2.5"
    assert q2.format_stat(float("nan")) == "-"
    # Block crawl can have 0 third-party requests. 0 is a value, not a missing crawl.
    assert q2.format_stat(0.0) == "0"


def test_q1_and_q2_agree_on_crawls_and_metrics() -> None:
    # Q2's load skips rows for unknown crawls, without a warning
    assert q2.MODES == q1.MODES
    assert q2.LABELS == q1.LABELS
    assert q2.METRICS == list(q1.METRICS.items())


# *******************************************
# Q2 input check, unit tests on load
# *******************************************


def test_load_accepts_extra_columns(tmp_path: Path) -> None:
    path = tmp_path / "input.csv"
    write_lf(path, f"{Q1_COLUMNS},note\ndesktop,ru.nl,3,1,1,1,hi\n")
    data = q2.load(str(path))
    assert data["desktop"]["requests"] == [3]


def test_load_names_every_missing_column(tmp_path: Path) -> None:
    path = tmp_path / "input.csv"
    write_lf(path, "crawl,website,requests,tp_requests\ndesktop,ru.nl,3,1\n")
    with pytest.raises(q2.MetricsFileError, match="missing columns tp_domains, tp_entities"):
        q2.load(str(path))


def test_load_rejects_empty_file(tmp_path: Path) -> None:
    path = tmp_path / "input.csv"
    write_lf(path, "")
    with pytest.raises(q2.MetricsFileError, match="crawl"):
        q2.load(str(path))
