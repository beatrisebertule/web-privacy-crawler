import csv
import os
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

IN_CSV = "./out/per_website_metrics.csv"
OUTDIR = "out"
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


def fmt(x):
    """Integers as ints; half-values (medians) keep one decimal."""
    return str(int(x)) if float(x) == int(x) else f"{x:.1f}"


def load(in_csv):
    data = {m: {key: [] for key, _ in METRICS} for m in MODES}
    with open(in_csv, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            mode = row["crawl"].strip().lower()
            if mode not in data:
                continue
            for key, _ in METRICS:
                data[mode][key].append(int(row[key]))
    return data


def stats(vals):
    a = np.array(vals, dtype=float)
    if a.size == 0:
        return {"Min": float("nan"), "Median": float("nan"), "Max": float("nan")}
    return {"Min": a.min(), "Median": np.median(a), "Max": a.max()}


if __name__ == "__main__":
    in_csv = sys.argv[1] if len(sys.argv) > 1 else IN_CSV

    data = load(in_csv)
    counts = {m: len(data[m]["requests"]) for m in MODES}
    summ = {key: {m: stats(data[m][key]) for m in MODES} for key, _ in METRICS}

    header = ["Metric"] + [f"{LABELS[m]} {s}" for m in MODES for s in STATS]
    wide = os.path.join(OUTDIR, "summary_table.csv")
    with open(wide, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        for key, label in METRICS:
            row = [label]
            for m in MODES:
                s = summ[key][m]
                row += [fmt(s["Min"]), fmt(s["Median"]), fmt(s["Max"])]
            w.writerow(row)

    long = os.path.join(OUTDIR, "summary_long.csv")
    with open(long, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["crawl", "metric", "min", "median", "max"])
        for key, label in METRICS:
            for m in MODES:
                s = summ[key][m]
                w.writerow([LABELS[m], label, fmt(s["Min"]), fmt(s["Median"]), fmt(s["Max"])])

    for m in MODES:
        p = os.path.join(OUTDIR, f"summary_{m}.csv")
        with open(p, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow([f"Metric ({LABELS[m]}, n={counts[m]})", "Min", "Median", "Max"])
            for key, label in METRICS:
                s = summ[key][m]
                w.writerow([label, fmt(s["Min"]), fmt(s["Median"]), fmt(s["Max"])])

    print("\nSummary (Min / Median / Max) per crawl   "
          f"[n={', '.join(f'{LABELS[m]} {counts[m]}' for m in MODES)}]\n")
    mw = max(len(l) for _, l in METRICS)
    print(" " * mw + "   " + "   ".join(f"{LABELS[m]:^20}" for m in MODES))
    print(" " * mw + "   " + "   ".join(f"{'Min':>5} {'Med':>6} {'Max':>5}" for _ in MODES))
    for key, label in METRICS:
        cells = []
        for m in MODES:
            s = summ[key][m]
            cells.append(f"{fmt(s['Min']):>5} {fmt(s['Median']):>6} {fmt(s['Max']):>5}")
        print(f"{label:<{mw}}   " + "   ".join(cells))

    print(f"\nWrote {wide}")
    print(f"Wrote {long}")
    print(f"Wrote {OUTDIR}/summary_<mode>.csv  (one per crawl)")
    print(f"Wrote {OUTDIR}/summary_table.png")