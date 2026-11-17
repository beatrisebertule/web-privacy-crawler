import csv
import os
import sys
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
OUTDIR = ROOT / "results"
IN_CSV = OUTDIR / "01_per_website_metrics.csv"           # written by 01_analysis.py
MODES = ["desktop", "mobile", "block", "ignore"]           # column order
LABELS = {"desktop": "Desktop", "mobile": "Mobile",
          "block": "Block", "ignore": "Ignore"}
METRICS = [                                                 # row order (1a-d)
    ("requests",    "Number of requests per website"),
    ("tp_requests", "Number of third-party requests per website"),
    ("tp_domains",  "Number of distinct third-party domains per website"),
    ("tp_entities", "Number of distinct third-party entities per website"),
]
STATS = ["Min", "Median", "Max"]


class MetricsFileError(ValueError):
    """Q1's per-website CSV is missing or lacks a column Q2 reads."""


def format_stat(value):
    """Integers as ints; half-values (medians) keep one decimal."""
    if np.isnan(value):  # crawl with no rows
        return "-"
    return str(int(value)) if float(value) == int(value) else f"{value:.1f}"


def load(in_csv):
    data = {m: {key: [] for key, _ in METRICS} for m in MODES}
    try:
        fh = open(in_csv, newline="", encoding="utf-8")
    except FileNotFoundError as missing:
        raise MetricsFileError(
            f"{in_csv} not found. 01_analysis.py writes it, run that first"
        ) from missing
    with fh:
        reader = csv.DictReader(fh)
        # `fieldnames` is None if file is empty
        columns = reader.fieldnames or []
        missing_columns = [
            column for column in ["crawl", *(key for key, _ in METRICS)]
            if column not in columns
        ]
        if missing_columns:
            noun = "column" if len(missing_columns) == 1 else "columns"
            raise MetricsFileError(
                f"{in_csv} is missing {noun} {', '.join(missing_columns)}. "
                f"01_analysis.py writes it, run that first"
            )
        for row in reader:
            mode = row["crawl"].strip().lower()
            if mode not in data:
                continue
            for key, _ in METRICS:
                data[mode][key].append(int(row[key]))
    return data


def stats(vals):
    values = np.array(vals, dtype=float)
    if values.size == 0:
        return {"Min": float("nan"), "Median": float("nan"), "Max": float("nan")}
    return {"Min": values.min(), "Median": np.median(values), "Max": values.max()}


if __name__ == "__main__":
    in_csv = sys.argv[1] if len(sys.argv) > 1 else IN_CSV

    try:
        data = load(in_csv)
    except MetricsFileError as input_error:
        print(f"Q2 stopped: {input_error}", file=sys.stderr)
        sys.exit(1)
    counts = {m: len(data[m]["requests"]) for m in MODES}
    for m in MODES:
        if counts[m] == 0:
            print(f'Q2 warning: no {LABELS[m]} rows in {in_csv}, its columns show "-"', file=sys.stderr)
    summ = {key: {m: stats(data[m][key]) for m in MODES} for key, _ in METRICS}

    header = ["Metric"] + [f"{LABELS[m]} {s}" for m in MODES for s in STATS]
    wide = os.path.join(OUTDIR, "02_summary_table.csv")
    with open(wide, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        for key, label in METRICS:
            row = [label]
            for m in MODES:
                s = summ[key][m]
                row += [format_stat(s["Min"]), format_stat(s["Median"]), format_stat(s["Max"])]
            w.writerow(row)

    long = os.path.join(OUTDIR, "02_summary_long.csv")
    with open(long, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["crawl", "metric", "min", "median", "max"])
        for key, label in METRICS:
            for m in MODES:
                s = summ[key][m]
                w.writerow([LABELS[m], label, format_stat(s["Min"]), format_stat(s["Median"]), format_stat(s["Max"])])

    for m in MODES:
        p = os.path.join(OUTDIR, f"summary_{m}.csv")
        with open(p, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow([f"Metric ({LABELS[m]}, n={counts[m]})", "Min", "Median", "Max"])
            for key, label in METRICS:
                s = summ[key][m]
                w.writerow([label, format_stat(s["Min"]), format_stat(s["Median"]), format_stat(s["Max"])])

    print("\nSummary (Min / Median / Max) per crawl   "
          f"[n={', '.join(f'{LABELS[m]} {counts[m]}' for m in MODES)}]\n")
    label_width = max(len(l) for _, l in METRICS)
    print(" " * label_width + "   " + "   ".join(f"{LABELS[m]:^20}" for m in MODES))
    print(" " * label_width + "   " + "   ".join(f"{'Min':>5} {'Med':>6} {'Max':>5}" for _ in MODES))
    for key, label in METRICS:
        cells = []
        for m in MODES:
            s = summ[key][m]
            cells.append(f"{format_stat(s['Min']):>5} {format_stat(s['Median']):>6} {format_stat(s['Max']):>5}")
        print(f"{label:<{label_width}}   " + "   ".join(cells))

    print(f"\nWrote {wide}")
    print(f"Wrote {long}")
    print(f"Wrote {OUTDIR}/02_summary_<mode>.csv  (one per crawl)")
    print(f"Wrote {OUTDIR}/02_summary_table.png")