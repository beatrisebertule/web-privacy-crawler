# #!/usr/bin/env python3
# """
# Metric (a) only: box plot of the number of requests per website across the four
# crawl modes (accept, reject, ublock, adguard).

# "Number of requests" = entries that received a response (response.status > 0),
# via get_num_requests(); blocked / failed requests do not count.

# Data layout: one folder per mode (crawler_data_<mode>/), each with ~30 website
# HARs named <domain>.har. Folders are matched to modes by keyword.

# Dependencies: matplotlib, numpy  (no tldextract / entities list needed here).
# Run:  python3 boxplot_requests.py            (reads ./)
#       python3 boxplot_requests.py ROOT
# """
# import glob
# import json
# import os
# import sys

# import matplotlib
# matplotlib.use("Agg")
# import matplotlib.pyplot as plt
# import numpy as np

# # ===== configuration (edit these) =====
# ROOT = "."
# OUTDIR = "analysis/plots"
# MODES = ["desktop", "mobile", "block", "ignore"]           # X-axis order
# LABELS = {"desktop": "Desktop", "mobile": "Mobile",
#           "block": "Block", "ignore": "Ignore"}
# # ======================================

# COLORS = ["#4e79a7", "#59a14f", "#e15759", "#f2a94e"]


# def response_received(entry: dict) -> bool:
#     """True if the request got an HTTP response (status > 0)."""
#     resp = entry.get("response") or {}
#     status = resp.get("status", 0)
#     return isinstance(status, int) and status > 0


# def get_num_requests(har: dict) -> int:
#     """(1) Number of requests that received a response."""
#     entries = har["log"]["entries"]
#     received = [entry
#                 for entry in entries
#                 if response_received(entry)]   # check if a response was received
#     return len(received)


# def find_mode_dir(root, mode):
#     cands = [e for e in sorted(os.listdir(root))
#              if os.path.isdir(os.path.join(root, e))]
#     wanted = {f"crawler_data_{mode}", f"crawl_data_{mode}", f"crawler_{mode}", mode}
#     exact = [e for e in cands if e.lower() in wanted]
#     contains = [e for e in cands if mode.lower() in e.lower()]
#     pick = exact[0] if exact else (contains[0] if contains else None)
#     return os.path.join(root, pick) if pick else None


# def main():
#     root = sys.argv[1] if len(sys.argv) > 1 else ROOT
#     dirs = {m: find_mode_dir(root, m) for m in MODES}
#     missing = [m for m in MODES if not dirs[m]]
#     if missing:
#         sys.exit(f"ERROR: no folder found for mode(s): {', '.join(missing)} under "
#                  f"'{root}'. Expected crawler_data_<mode>/. Edit MODES if needed.")

#     os.makedirs(OUTDIR, exist_ok=True)
#     data = {}
#     for m in MODES:
#         files = sorted(glob.glob(os.path.join(dirs[m], "**", "*.har"), recursive=True))
#         print(f"\nProcessing {m}...  ({len(files)} websites)")
#         counts = []
#         for path in files:
#             try:
#                 with open(path, "r", encoding="utf-8", errors="replace") as f:
#                     har = json.load(f)
#             except (ValueError, OSError) as e:
#                 print(f"  ! skip {os.path.basename(path)}: {e}", file=sys.stderr)
#                 continue
#             counts.append(get_num_requests(har))
#         data[m] = counts
#         if counts:
#             print(f"  median {np.median(counts):.0f} requests")

#     if not any(data.values()):
#         sys.exit("ERROR: mode folders found but no .har files inside.")

#     fig, ax = plt.subplots(figsize=(7, 5))
#     series = [data[m] for m in MODES]
#     bp = ax.boxplot(series, positions=range(1, len(MODES) + 1), showfliers=True,
#                     patch_artist=True,
#                     medianprops=dict(color="#b2182b", linewidth=1.8),
#                     flierprops=dict(marker="o", markersize=3, markerfacecolor="none",
#                                     markeredgecolor="#888", alpha=0.6),
#                     whiskerprops=dict(color="#555"), capprops=dict(color="#555"),
#                     boxprops=dict(edgecolor="#555"))
#     for patch, col in zip(bp["boxes"], COLORS):
#         patch.set_facecolor(col)
#         patch.set_alpha(0.65)
#     ax.set_title("Number of requests per website")
#     ax.set_ylabel("requests per website")
#     ax.grid(axis="y", linestyle=":", alpha=0.5)
#     ax.set_xticks(range(1, len(MODES) + 1))
#     ax.set_xticklabels([f"{LABELS.get(m, m)}\n(n={len(data[m])})" for m in MODES])
#     fig.tight_layout()
#     out = os.path.join(OUTDIR, "boxplot_requests.png")
#     fig.savefig(out, dpi=150)
#     print(f"\nWrote {out}")


# if __name__ == "__main__":
#     main()

#!/usr/bin/env python3
"""
Compare four crawl modes with box plots, one plot per metric.

Metrics (one box plot each):
    (a) Number of requests per website            -> get_num_requests()
    (b) Number of third-party requests per website
    (c) Number of distinct third-party domains per website
    (d) Number of distinct third-party entities per website (Disconnect entities)

Data layout
-----------
One folder per mode, each holding ~30 website HARs named <domain>.har:

    crawler_data_desktop/  trekpleister.nl.har   ... (30 files)
    crawler_data_mobile/   trekpleister.nl.har   ...
    crawler_data_block/    trekpleister.nl.har   ...
    crawler_data_ignore/   trekpleister.nl.har   ...

The mode folders live under ROOT. A folder is matched to a mode by keyword, so
crawler_data_desktop / crawl_data_desktop / desktop all work. The first-party
domain of each site is taken from the HAR file name (a trailing _<mode> is
stripped too, so trekpleister.nl_accept.har also works).

Run:  python3 har_boxplots.py                 (reads ./ and ./entities.json)
      python3 har_boxplots.py ROOT ENTITIES_JSON
"""
import csv
import glob
import json
import os
import sys
from collections import OrderedDict
from urllib.parse import urlsplit

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import tldextract

# ===== configuration (edit these) ==========================================
ROOT = "."                         # folder that holds the crawler_data_<mode> dirs
ENTITIES = "./entities.json"         # Disconnect entities list (for metric d)
OUTDIR = "./analysis/out"

# the four crawl modes, in X-axis order (these are the <mode> in crawler_data_<mode>)
MODES = ["desktop", "mobile", "block", "ignore"]
LABELS = {"desktop": "Desktop", "mobile": "Mobile",
          "block": "Block", "ignore": "Ignore"}
COUNT_UNKNOWN_AS_ENTITY = True     # metric (d): unknown domain = its own entity
# ===========================================================================

METRICS = OrderedDict([
    ("requests",    "Number of requests per website"),
    ("tp_requests", "Number of third-party requests per website"),
    ("tp_domains",  "Number of distinct third-party domains per website"),
    ("tp_entities", "Number of distinct third-party entities per website"),
])

_EXTRACT = tldextract.TLDExtract(suffix_list_urls=())  # bundled PSL, no network


# ---- helpers --------------------------------------------------------------
def etld1(host):
    if not host:
        return ""
    host = host.strip().lower().rstrip(".")
    if _is_ip(host) or host.startswith("["):
        return host
    r = _EXTRACT(host)
    reg = getattr(r, "top_domain_under_public_suffix", None) or r.registered_domain
    return reg or r.domain or host


def _is_ip(host):
    p = host.split(".")
    return len(p) == 4 and all(x.isdigit() for x in p)


def host_of(url):
    try:
        netloc = urlsplit(url).netloc
    except ValueError:
        return ""
    if "@" in netloc:
        netloc = netloc.rsplit("@", 1)[1]
    if netloc.startswith("["):
        return netloc.split("]")[0].lstrip("[")
    return netloc.split(":")[0]


def response_received(entry):
    """True if the request got an HTTP response (status > 0).
    Blocked / aborted / failed requests are logged with status 0."""
    resp = entry.get("response") or {}
    status = resp.get("status", 0)
    return isinstance(status, int) and status > 0


def get_num_requests(har: dict) -> int:
    """(1) Number of requests that received a response."""
    entries = har["log"]["entries"]
    received = [entry
                for entry in entries
                if response_received(entry)]   # check if a response was received
    return len(received)


# ---- Disconnect entities --------------------------------------------------
def load_entity_map(path):
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    ents = data.get("entities", data)
    dmap = {}
    for name, obj in ents.items():
        for d in list(obj.get("resources", [])) + list(obj.get("properties", [])):
            key = etld1(d)
            if key:
                dmap.setdefault(key, name)
    return dmap


def entity_of(domain, dmap):
    if domain in dmap:
        return dmap[domain]
    return domain if COUNT_UNKNOWN_AS_ENTITY else None


# ---- per-HAR metrics ------------------------------------------------------
def analyse_har(har, first_party, dmap):
    """All four metrics for one already-loaded HAR dict."""
    fp = etld1(first_party)
    entries = (har.get("log") or {}).get("entries") or []

    n_req = 0
    n_tp = 0
    tp_domains = set()
    tp_entities = set()
    for ent in entries:
        if not response_received(ent):        # skip blocked / failed requests
            continue
        n_req += 1                            # (a) every responded request
        url = (ent.get("request") or {}).get("url", "")
        if not url.lower().startswith(("http://", "https://")):
            continue
        dom = etld1(host_of(url))
        if not dom:
            continue
        if dom != fp:                         # third party
            n_tp += 1
            tp_domains.add(dom)
            e = entity_of(dom, dmap)
            if e is not None:
                tp_entities.add(e)
    return {"requests": n_req, "tp_requests": n_tp,
            "tp_domains": len(tp_domains), "tp_entities": len(tp_entities)}


# ---- discovery ------------------------------------------------------------
def find_mode_dir(root, mode):
    """Sub-dir of root for a mode: crawler_data_<mode> / crawl_data_<mode> /
    <mode>, or the first dir whose name contains the mode keyword."""
    cands = [e for e in sorted(os.listdir(root))
             if os.path.isdir(os.path.join(root, e))]
    wanted = {f"crawler_data_{mode}", f"crawl_data_{mode}", f"crawler_{mode}", mode}
    exact = [e for e in cands if e.lower() in wanted]
    contains = [e for e in cands if mode.lower() in e.lower()]
    pick = exact[0] if exact else (contains[0] if contains else None)
    return os.path.join(root, pick) if pick else None


def domain_from_filename(path, mode):
    base = os.path.basename(path)
    if base.lower().endswith(".har"):
        base = base[:-4]
    if base.lower().endswith("_" + mode.lower()):   # tolerate <domain>_<mode>.har
        base = base[: -(len(mode) + 1)]
    return base


def har_files(folder):
    return sorted(glob.glob(os.path.join(folder, "**", "*.har"), recursive=True))


# ---- plotting -------------------------------------------------------------
def boxplot(ax, data_by_mode, title):
    data = [data_by_mode.get(m, []) for m in MODES]
    bp = ax.boxplot(data, positions=range(1, len(MODES) + 1), showfliers=True,
                    patch_artist=True,
                    medianprops=dict(color="#b2182b", linewidth=1.8),
                    flierprops=dict(marker="o", markersize=3, markerfacecolor="none",
                                    markeredgecolor="#888", alpha=0.6),
                    whiskerprops=dict(color="#555"), capprops=dict(color="#555"),
                    boxprops=dict(edgecolor="#555"))
    colors = ["#4e79a7", "#59a14f", "#e15759", "#f2a94e"]
    for patch, col in zip(bp["boxes"], colors):
        patch.set_facecolor(col)
        patch.set_alpha(0.65)
    ax.set_title(title, fontsize=11)
    ax.set_ylabel("count per website")
    ax.grid(axis="y", linestyle=":", alpha=0.5)
    ns = [len(data_by_mode.get(m, [])) for m in MODES]
    ax.set_xticks(range(1, len(MODES) + 1))
    ax.set_xticklabels([f"{LABELS.get(m, m)}\n(n={n})" for m, n in zip(MODES, ns)])


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else ROOT
    entities = sys.argv[2] if len(sys.argv) > 2 else ENTITIES
    if not os.path.exists(entities):
        sys.exit(f"ERROR: entities file not found: '{entities}'. "
                 f"Put entities.json here or pass it as the 2nd argument.")

    dirs = {m: find_mode_dir(root, m) for m in MODES}
    missing = [m for m in MODES if not dirs[m]]
    if missing:
        sys.exit(f"ERROR: no folder found for mode(s): {', '.join(missing)} under "
                 f"'{root}'. Expected crawler_data_<mode>/ (e.g. crawler_data_accept/). "
                 f"Edit MODES at the top if your modes are named differently.")

    dmap = load_entity_map(entities)
    print(f"Loaded {len(dmap)} domain->entity mappings.")

    os.makedirs(OUTDIR, exist_ok=True)
    per_mode = {k: {m: [] for m in MODES} for k in METRICS}
    all_rows = []

    for m in MODES:                                     # mirrors your loop
        files = har_files(dirs[m])
        print(f"\nProcessing {m}...  ({len(files)} websites in {dirs[m]})")
        records = []
        for path in files:
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    har = json.load(f)
            except (ValueError, OSError) as e:
                print(f"  ! skip {os.path.basename(path)}: {e}", file=sys.stderr)
                continue
            domain = domain_from_filename(path, m)
            res = analyse_har(har, domain, dmap)
            res["website"] = domain
            records.append(res)
            for k in METRICS:
                per_mode[k][m].append(res[k])
            all_rows.append({"crawl": m, **res})
        jpath = os.path.join(OUTDIR, f"metrics_{m}.json")
        with open(jpath, "w", encoding="utf-8") as jf:
            json.dump(records, jf, indent=2)
        print(f"  wrote {jpath}")

    if not all_rows:
        sys.exit("ERROR: mode folders found but they contain no .har files.")

    # combined CSV
    csv_path = os.path.join(OUTDIR, "per_website_metrics.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["crawl", "website", "requests", "tp_requests",
                    "tp_domains", "tp_entities"])
        for r in all_rows:
            w.writerow([r["crawl"], r["website"], r["requests"],
                        r["tp_requests"], r["tp_domains"], r["tp_entities"]])
    print(f"\nWrote {csv_path} ({len(all_rows)} rows)")

    # summary
    print("\nMedian (mean) per mode:")
    print("metric".ljust(34) + "".join(LABELS.get(m, m).rjust(14) for m in MODES))
    for k in METRICS:
        line = k.ljust(34)
        for m in MODES:
            vals = per_mode[k][m]
            line += (f"{np.median(vals):.0f} ({np.mean(vals):.1f})".rjust(14)
                     if vals else "-".rjust(14))
        print(line)

    # one box plot per metric
    for k, label in METRICS.items():
        fig, ax = plt.subplots(figsize=(7, 5))
        boxplot(ax, per_mode[k], label)
        fig.tight_layout()
        p = os.path.join(OUTDIR, f"boxplot_{k}.png")
        fig.savefig(p, dpi=150)
        plt.close(fig)
        print(f"Wrote {p}")

    # combined 2x2
    fig, axes = plt.subplots(2, 2, figsize=(13, 10))
    for ax, (k, label) in zip(axes.flat, METRICS.items()):
        boxplot(ax, per_mode[k], f"({'abcd'[list(METRICS).index(k)]}) {label}")
    fig.suptitle("Tracking metrics across crawls", fontsize=14)
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    p = os.path.join(OUTDIR, "boxplots_combined.png")
    fig.savefig(p, dpi=150)
    plt.close(fig)
    print(f"Wrote {p}")


if __name__ == "__main__":
    main()
