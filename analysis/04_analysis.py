import csv
import glob
import json
import os
import sys
from collections import OrderedDict
from pathlib import Path
from urllib.parse import urlsplit

import statistics

from tld import get_fld

from final_page import final_page_host

ROOT = Path(__file__).resolve().parent.parent  # repo root, holds the crawl_data_<mode> dirs
ENTITIES = ROOT / "crawler_src" / "entities.json"      # disconnect entities list (for metric d)
OUTDIR = ROOT / "results"
# Q2 reads Q1's per-website CSV. Names here must differ from it.
METRICS_CSV = "04_per_website_metrics_desktop.csv"
SUMMARY_CSV = "04_summary_desktop.csv"

TLD_COUNTRY = {"edu": "us", "nl": "nl", "uk": "uk"}

# the four crawl modes, in X-axis order (these are the <mode> in crawler_data_<mode>)
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


def country_from_domain(domain):
    tld = domain.lower().rstrip(".").rsplit(".", 1)[-1]
    return TLD_COUNTRY.get(tld, "other")


if __name__ == "__main__":
    
    root = sys.argv[1] if len(sys.argv) > 1 else ROOT
    entities = sys.argv[2] if len(sys.argv) > 2 else ENTITIES

    dmap = load_entity_map(entities)
    print(f"Loaded {len(dmap)} domain->entity mappings.")

    all_rows = []

    mode = "Desktop"
    folder = os.path.join(ROOT, "crawl_data_desktop")
    # return directory of a specific mode
    files = har_files(os.path.join(ROOT, "crawl_data_desktop"))

    print(f"\nProcessing {mode}...  ({len(files)} websites in {folder})")
    # loop over all har files within a directory of a specific mode
    for path in files:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                har = json.load(f)
        except (ValueError, OSError) as e:
            print(f"  ! skip {os.path.basename(path)}: {e}", file=sys.stderr)
            continue
        
        domain = domain_from_filename(path, mode)          # return a domain name (strip directory path away)
        country = country_from_domain(domain)
        res = analyse_har(har, final_page_host(har, domain), dmap)   # first party is the page after redirects
        res["website"] = domain
        res["country"] = country

        all_rows.append(res)

    os.makedirs(OUTDIR, exist_ok=True)

    # create result CSV file 
    csv_path = os.path.join(OUTDIR, METRICS_CSV)
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["country", "website", "requests", "tp_requests",
                    "tp_domains", "tp_entities"])
        for r in all_rows:
            w.writerow([r["country"], r["website"], r["requests"],
                        r["tp_requests"], r["tp_domains"], r["tp_entities"]])
    print(f"\nWrote {csv_path} ({len(all_rows)} rows)")


    summary_path = os.path.join(OUTDIR, SUMMARY_CSV)
    with open(summary_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["country", "metric", "min", "median", "max"])
        for country in ["nl", "uk", "us"]:
            for metric in METRICS:
                vals = [row[metric] for row in all_rows if row["country"] == country]
                if vals:
                    w.writerow([country, metric, min(vals), statistics.median(vals), max(vals)])
    print(f"Wrote {summary_path}")
