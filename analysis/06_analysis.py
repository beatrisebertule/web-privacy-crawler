import csv
import glob
import json
import os
import sys
from collections import defaultdict
from urllib.parse import urlsplit
from tld import get_fld
import pprint

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
        fp = fld(website) # return extended TLD
        
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                har = json.load(f)
        except (ValueError, OSError) as e:
            print(f"  ! skip {base}: {e}", file=sys.stderr)
            continue
        
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


def render_table(a_rows, b_rows, path):
    n = max(len(a_rows), len(b_rows), 1)
    a_top = a_rows + [("", "")] * (n - len(a_rows))
    b_top = b_rows + [("", "")] * (n - len(b_rows))

    group = [f"Domains observed in Crawl-{CRAWL_DESKTOP.capitalize()}", "",
             f"Domains observed in Crawl-{CRAWL_MOBILE.capitalize()}", ""]
    sub = ["Domain", "Site count ↓", "Domain", "Site count ↓"]
    body = []
    for (ad, ac), (bd, bc) in zip(a_top, b_top):
        body.append([ad, str(ac) if ac != "" else "", bd, str(bc) if bc != "" else ""])
    cell_text = [group, sub] + body

    fig_w = 11
    fig, ax = plt.subplots(figsize=(fig_w, 0.6 + 0.5 * len(cell_text)))
    ax.axis("off")
    col_w = [0.34, 0.16, 0.34, 0.16]
    tbl = ax.table(cellText=cell_text, colWidths=col_w, cellLoc="center", loc="center")
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(10)
    tbl.scale(1, 1.6)
    for (r, c), cell in tbl.get_celld().items():
        if r == 0:                                # group header, span 2 cols each
            cell.set_text_props(weight="bold")
            cell.visible_edges = "TBL" if c in (0, 2) else "TBR"
        elif r == 1:
            cell.set_text_props(weight="bold")
        if c in (0, 2) and r >= 1:
            cell.set_text_props(ha="left")
            cell.PAD = 0.04
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    a, b = CRAWL_DESKTOP, CRAWL_MOBILE
    da, db = DIR_DESKTOP, DIR_MOBILE

    for d in (da, db):
        if not os.path.isdir(d):
            sys.exit(f"ERROR: crawl folder not found: {d}")
            
    a_sites = collect_tp_domains(da) # dictionary
    b_sites = collect_tp_domains(db) # dictionary
    
    # pp = pprint.PrettyPrinter(indent=4, width=50)
    # pp.pprint(a_sites)
    # print('\n\n')
    # pp.pprint(b_sites)
    
    a_domains, b_domains = set(a_sites), set(b_sites) # return a set of unique keys - 3rd party domains contacted
    print(f"\nDistinct third-party domains: {a.capitalize()}={len(a_domains)}, "
          f"{b.capitalize()}={len(b_domains)}, shared={len(a_domains & b_domains)}\n")
    
    # return contacted 3rd party domains that were not present in teh other crawl mode
    a_only = exclusive_ranked(a_sites, b_domains)   # a) desktop-only
    b_only = exclusive_ranked(b_sites, a_domains)   # b) mobile-only

    os.makedirs(OUTDIR, exist_ok=True)
    # full ranked CSVs
    for name, rows in ((a, a_only), (b, b_only)):
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
    show(f"a) Contacted in {a.capitalize()} but NEVER in {b.capitalize()}", a_only)
    show(f"b) Contacted in {b.capitalize()} but NEVER in {a.capitalize()}", b_only)

    render_table(a_only, b_only, os.path.join(OUTDIR, "exclusive_domains.png"))
    print(f"\nWrote {OUTDIR}/exclusive_domains.png")