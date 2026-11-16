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
# import tldextract
from tld import get_fld

from final_page import final_page_host
from plot_text import CRAWL_AXIS_LABEL

ROOT = "."                         # folder that holds the crawler_data_<mode> dirs
ENTITIES = "./entities.json"       # disconnect entities list (for metric d)
OUTDIR = "results"
METRICS_CSV = "q1_per_website_metrics.csv"  # Q2 reads this

# the four crawl modes, in X-axis order (these are the <mode> in crawler_data_<mode>)
MODES = ["desktop", "mobile", "block", "ignore"]
LABELS = {"desktop": "Desktop", "mobile": "Mobile",
          "block": "Block", "ignore": "Ignore"}
COUNT_UNKNOWN_AS_ENTITY = True     # metric (d): unknown domain = its own entity

METRICS = OrderedDict([
    ("requests",    "Number of requests per website"),
    ("tp_requests", "Number of third-party requests per website"),
    ("tp_domains",  "Number of distinct third-party domains per website"),
    ("tp_entities", "Number of distinct third-party entities per website"),
])


def fld(host):
    """eTLD+1 for a bare hostname or URL; '' if it can't be parsed."""
    if not host:
        return ""
    host = host.strip().lower().rstrip(".")
    if _is_ip(host):                      # keep IPs as their own "domain"
        return host
    return get_fld(host, fix_protocol=True, fail_silently=True) or ""


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


# ----
# Load Entity map
# ----

def load_entity_map(path):
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    ents = data.get("entities", data)
    dmap = {}
    for name, obj in ents.items():
        for d in list(obj.get("resources", [])) + list(obj.get("properties", [])):
            key = fld(d)
            if key:
                dmap.setdefault(key, name)
    return dmap


def entity_of(domain, dmap):
    if domain in dmap:
        return dmap[domain]
    return domain if COUNT_UNKNOWN_AS_ENTITY else None


# ---
# Analyze har files
# ---

def analyse_har(har, first_party, dmap):
    """All four metrics for one already-loaded HAR dict."""
    fp = fld(first_party)
    entries = (har.get("log") or {}).get("entries") or []

    n_req = 0              # (a) total requests that got a response
    n_tp = 0               # (b) how many of those were third-party
    tp_domains = set()     # (c) distinct third-party eTLD+1 domains (a set = no duplicates)
    tp_entities = set()    # (d) distinct third-party entities (Disconnect owners)
    
    for ent in entries:
        if not response_received(ent):        # skip blocked / failed requests
            continue
        
        n_req += 1                            # (a) every responded request
        url = ent["request"]["url"]           # get url of every request
        
        if not url.lower().startswith(("http://", "https://")):   # continue only wiht http/https requests
            continue
        
        dom = fld(host_of(url))
        if not dom:                           # skip unparsable hosts
            continue
        
        # sanity check
        # print(f"fp: {fp}")
        # print(f"dom: {dom}")
        # print(f"frp != dom: {dom != fp}")
        
        if dom != fp:                         # this request is THIRD PARTY
            n_tp += 1                         # (b) count the third-party request
            tp_domains.add(dom)               # (c) remember the distinct domain
            
            e = entity_of(dom, dmap)          # map domain to a known entity name
            if e is not None:
                tp_entities.add(e)            # (d) eturns the owner name if known 
                
    # return results
    return {"requests": n_req, "tp_requests": n_tp,
            "tp_domains": len(tp_domains), "tp_entities": len(tp_entities)}


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

# ---
# Plot box plots
# ---

def boxplot(ax, data_by_mode, metric_label):
    data = [data_by_mode.get(m, []) for m in MODES]
    bp = ax.boxplot(data, positions=range(1, len(MODES) + 1), showfliers=True,
                    patch_artist=True,
                    medianprops=dict(color="#b2182b", linewidth=1.8),
                    flierprops=dict(marker="x", markersize=3, markerfacecolor="none",
                                    markeredgecolor="#888", alpha=0.8),
                    whiskerprops=dict(color="#555"), capprops=dict(color="#555"),
                    boxprops=dict(edgecolor="#555"))
    colors = ["#4e79a7", "#59a14f", "#e15759", "#f2a94e"]
    for patch, col in zip(bp["boxes"], colors):
        patch.set_facecolor(col)
        patch.set_alpha(0.65)
    # ax.set_title(title, fontsize=11)
    # Single plots have no title of their own. Metric name on Y axis.
    ax.set_xlabel(CRAWL_AXIS_LABEL)
    ax.set_ylabel(metric_label)
    ax.grid(axis="y", linestyle=":", alpha=0.5)
    ns = [len(data_by_mode.get(m, [])) for m in MODES]
    ax.set_xticks(range(1, len(MODES) + 1))
    ax.set_xticklabels([f"{LABELS.get(m, m)}\n(n={n})" for m, n in zip(MODES, ns)])


if __name__ == "__main__":
    
    root = sys.argv[1] if len(sys.argv) > 1 else ROOT
    entities = sys.argv[2] if len(sys.argv) > 2 else ENTITIES
 
    # create a list of directories that contain har files per mode
    dirs = {m: find_mode_dir(root, m) for m in MODES}

    dmap = load_entity_map(entities)
    print(f"Loaded {len(dmap)} domain->entity mappings.")

    per_mode = {k: {m: [] for m in MODES} for k in METRICS}
    all_rows = []

    for m in MODES:    
        # return directory of a specific mode                                
        files = har_files(dirs[m])
        print(f"\nProcessing {m}...  ({len(files)} websites in {dirs[m]})")
        records = []
        # loop over all har files within a directory of a specific mode
        for path in files:
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    har = json.load(f)
            except (ValueError, OSError) as e:
                print(f"  ! skip {os.path.basename(path)}: {e}", file=sys.stderr)
                continue
            
            domain = domain_from_filename(path, m)          # return a domain name (strip directory path away)
            res = analyse_har(har, final_page_host(har, domain), dmap)   # first party is the page after redirects
            res["website"] = domain
            records.append(res)

            for k in METRICS:
                per_mode[k][m].append(res[k])
            all_rows.append({"crawl": m, **res})
        jpath = os.path.join(OUTDIR, f"metrics_{m}.json")
        
        os.makedirs(OUTDIR, exist_ok=True)
        with open(jpath, "w", encoding="utf-8") as jf:      # write results to a json file
            json.dump(records, jf, indent=2)
        print(f"  wrote {jpath}")

    # create result CSV file 
    csv_path = os.path.join(OUTDIR, METRICS_CSV)
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["crawl", "website", "requests", "tp_requests",
                    "tp_domains", "tp_entities"])
        for r in all_rows:
            w.writerow([r["crawl"], r["website"], r["requests"],
                        r["tp_requests"], r["tp_domains"], r["tp_entities"]])
    print(f"\nWrote {csv_path} ({len(all_rows)} rows)")

    # print summary of results
    print("\nMedian (mean) per mode:")
    print("metric".ljust(34) + "".join(LABELS.get(m, m).rjust(14) for m in MODES))
    for k in METRICS:
        line = k.ljust(34)
        for m in MODES:
            vals = per_mode[k][m]
            line += (f"{np.median(vals):.0f} ({np.mean(vals):.1f})".rjust(14)
                     if vals else "-".rjust(14))
        print(line)
    print('\n')

    # plot one box plot per metric
    for k, label in METRICS.items():
        fig, ax = plt.subplots(figsize=(7, 5))
        boxplot(ax, per_mode[k], label)
        fig.tight_layout()
        p = os.path.join(OUTDIR, f"boxplot_{k}.png")
        fig.savefig(p, dpi=150)
        plt.close(fig)
        print(f"Wrote {p}")

    # combine all boxplots in one plot
    fig, axes = plt.subplots(2, 2, figsize=(13, 10))
    for ax, (k, label) in zip(axes.flat, METRICS.items()):
        boxplot(ax, per_mode[k], label)
    fig.suptitle("Tracking metrics across crawls", fontsize=14)
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    p = os.path.join(OUTDIR, "boxplots_combined.png")
    fig.savefig(p, dpi=150)
    plt.close(fig)
    print(f"Wrote {p}")
