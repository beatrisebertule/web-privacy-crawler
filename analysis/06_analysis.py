import csv
import glob
import json
import os
import sys
from collections import defaultdict
from urllib.parse import urlsplit
from tld import get_fld
import pprint
import matplotlib.pyplot as plt

from final_page import final_page_host

DIR_DESKTOP = "./crawl_data_desktop"
DIR_MOBILE = "./crawl_data_mobile"
CRAWL_DESKTOP = "desktop"
CRAWL_MOBILE = "mobile"
OUTDIR = "results"


def fld(host):
    """eTLD+1 for a bare hostname or URL; '' if it can't be parsed."""
    if not host:
        return ""
    host = host.strip().lower().rstrip(".")
    return get_fld(host, fix_protocol=True, fail_silently=True) or ""


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

def collect_tp_domains(folder):
    """third-party domain -> set of distinct websites that contacted it.
    Keys are third-party domains (eTLD+1), e.g. "doubleclick.net".
    Values are sets of the visited websites (first-party eTLD+1) that contacted that domain at least once, e.g. {"berkeley.edu", "harvard.edu"}.""" 
    
    dom_sites = defaultdict(set)
    
    # loop over all .har files within a crawl data folder
    for path in sorted(glob.glob(os.path.join(folder, "**", "*.har"), recursive=True)):
        
        base = os.path.basename(path)
        website = base[:-4] if base.lower().endswith(".har") else base # strip away .har

        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                har = json.load(f)
        except (ValueError, OSError) as e:
            print(f"  ! skip {base}: {e}", file=sys.stderr)
            continue

        fp = fld(final_page_host(har, website)) # first party is the page after redirects

        entries = har.get("log")
        for entry in (entries or {}).get("entries") or []:
            
            # skip blocked/failed requests that did not receive any response
            if not response_received(entry):
                continue
            
            url = (entry.get("request") or {}).get("url", "")
            
            # continue only wiht http/https requests
            if not url.lower().startswith(("http://", "https://")):
                continue
            
            # return extended TLD
            dom = fld(host_of(url))
            if dom and dom != fp:                 # identify 3rd party request
                dom_sites[dom].add(fp)            # add 1st party domain that contacted that particular 3rd party
  
    return dom_sites


def exclusive_ranked(a_sites, b_domains):
    """Domains in crawl A not present at all in crawl B, ranked by site count.
    a_sites: the dict from collect_tp_domains for crawl A: {domain: {sites}}.
    b_domains: a set of all third-party domains seen in crawl B."""
    
    # loop over every (domain, set_of_sites) pair in crawl A, keeps a domain only if it’s absent from crawl B, turns each kept pair into a tuple (domain, number_of_sites)
    rows = [(d, len(sites)) for d, sites in a_sites.items() if d not in b_domains]
    rows.sort(key=lambda t: (-t[1], t[0])) # count desc, then name
    return rows


def render_csv(desktop_rows, mobile_rows, path):
    """Export desktop-only and mobile-only domains side by side as CSV."""
    n = max(len(desktop_rows), len(mobile_rows))

    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)

        # CSV header
        w.writerow([
            "desktop_only_domain",
            "desktop_site_count",
            "mobile_only_domain",
            "mobile_site_count"
        ])

        # Write both ranked lists side by side
        for i in range(n):
            desktop_domain, desktop_count = desktop_rows[i] if i < len(desktop_rows) else ("", "")
            mobile_domain, mobile_count = mobile_rows[i] if i < len(mobile_rows) else ("", "")

            w.writerow([desktop_domain, desktop_count, mobile_domain, mobile_count])


if __name__ == "__main__":
    desktop_crawl, mobile_crawl = CRAWL_DESKTOP, CRAWL_MOBILE
    desktop_dir, mobile_dir = DIR_DESKTOP, DIR_MOBILE

    for d in (desktop_dir, mobile_dir):
        if not os.path.isdir(d):
            sys.exit(f"ERROR: crawl folder not found: {d}")
            
    desktop_sites = collect_tp_domains(desktop_dir) # dictionary
    mobile_sites = collect_tp_domains(mobile_dir) # dictionary
    
    desktop_domains, mobile_domains = set(desktop_sites), set(mobile_sites) # return a set of unique keys - 3rd party domains contacted
    print(f"\nDistinct third-party domains: {desktop_crawl.capitalize()}={len(desktop_domains)}, "
          f"{mobile_crawl.capitalize()}={len(mobile_domains)}, shared={len(desktop_domains & mobile_domains)}\n")
    
    # return contacted 3rd party domains that were not present in teh other crawl mode
    desktop_only = exclusive_ranked(desktop_sites, mobile_domains)   # a) desktop-only
    mobile_only = exclusive_ranked(mobile_sites, desktop_domains)   # b) mobile-only

    os.makedirs(OUTDIR, exist_ok=True)
    # full ranked CSVs
    for name, rows in ((desktop_crawl, desktop_only), (mobile_crawl, mobile_only)):
        p = os.path.join(OUTDIR, f"exclusive_{name}_only.csv")
        with open(p, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["domain", "site_count"])
            w.writerows(rows)
        print(f"Wrote {p} ({len(rows)} domains)")

    # display results
    def show(title, rows):
        print(f"\n{title}")
        print("  " + "domain".ljust(34) + "site_count")
        for d, c in rows:
            print("  " + d.ljust(34) + str(c))
            
    show(f"a) Contacted in {desktop_crawl.capitalize()} but NEVER in {mobile_crawl.capitalize()}", desktop_only)
    show(f"b) Contacted in {mobile_crawl.capitalize()} but NEVER in {desktop_crawl.capitalize()}", mobile_only)

    csv_path = os.path.join(OUTDIR, "06_exclusive_domains.csv")
    render_csv(desktop_only, mobile_only, csv_path)

    print(f"Wrote {csv_path}")