import json
import sys
from pathlib import Path
from urllib.parse import urlsplit
 
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from tld import get_fld

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "crawler_src"))
from crawler import (
    DISCONNECT_SERVICES_PATH,
    listed_categories,
    load_disconnect_categories,
)
from final_page import final_page_host

OUTDIR = ROOT / "results"

def third_party_domains(har):
    """Returns the set of third party domains (eTLD+1) a page sent requests to"""
    website = har.stem.split("_")[0]

    with open(har, encoding="utf-8") as f:
        har = json.load(f)

    # First party is the page after redirects, not the file name
    first_party = get_fld(final_page_host(har, website), fix_protocol=True, fail_silently=True)

    domains = set()

    for entry in har["log"]["entries"]:
        if entry["response"]["status"] <= 0:  # If the request was blocked, skip it
            continue
        hostname = urlsplit(entry["request"]["url"]).hostname
        if not hostname:
            continue
        domain = get_fld(hostname, fix_protocol=True, fail_silently=True)
        if domain and domain != first_party:  # Only add if it's actually a third-party domain
            domains.add(domain)
    return domains

def categories_of_as_string(domain, categories_by_host):
    """Return the Disconnect categories of a domain as a string, or 'NA' if absent"""
    categories = sorted(listed_categories(domain, categories_by_host))
    if len(categories) == 0:
        return "NA"
    categories_string = categories[0]
    for cat in categories[1:]:
        categories_string += ", " + cat
    return categories_string

def plot(rows, crawl):
    """Plot table of the most prevalent third-party domains in a crawl"""
    fig, ax = plt.subplots(figsize=(8,5))
    ax.axis("off")

    table = ax.table(
        cellText=rows,
        colLabels=["Third-party domain", "Number of distinct websites ↓", "Disconnect categories"],
        cellLoc="center",
        loc="center",
    )

    for col in range(3):
        table[0, col].set_text_props(weight="bold")
 
    out = OUTDIR / f"top_domains_{crawl.lower()}.png"
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)

def domains_of_crawl(folder):
    """Return a list with all the contacted third-party domains per website in a crawl"""
    domains = []
    for har in folder.glob("*.har"):
        domains.append(third_party_domains(har))
    return domains

def count_sites_per_domain(sites):
    """Return a dictonary with the number of sites that contacted each third-party domain"""
    counts = {}
    for contacted in sites:
        for domain in contacted: # a set, so each site counts at most once per domain
            counts[domain] = counts.get(domain, 0) + 1
    return counts

def number_of_sites(item):
    """Return the number of sites of a (domain, n.o. sites) pair, used to sort the domains"""
    return item[1]

def top_domains(sites, categories_by_host):
    """Return the top 10 most prevalent third-party domains as rows: (domain, n.o. sites, categories)"""
    counts = count_sites_per_domain(sites)
    ranked = sorted(counts.items())
    ranked = sorted(ranked, key=number_of_sites, reverse=True)
    rows = []
    for domain, n_sites in ranked[:10]:
        rows.append((domain, n_sites, categories_of_as_string(domain, categories_by_host)))
    return rows

if __name__ == "__main__":
    categories_by_host = load_disconnect_categories(DISCONNECT_SERVICES_PATH)

    desktop_domains = domains_of_crawl(ROOT / "crawl_data_desktop")
    mobile_domains = domains_of_crawl(ROOT / "crawl_data_mobile")
    blocked_domains = domains_of_crawl(ROOT / "crawl_data_block")
    ignored_domains = domains_of_crawl(ROOT / "crawl_data_ignore")

    plot(top_domains(desktop_domains, categories_by_host), "Desktop")
    plot(top_domains(mobile_domains, categories_by_host), "Mobile")
    plot(top_domains(blocked_domains, categories_by_host), "Block")
    plot(top_domains(ignored_domains, categories_by_host), "Ignore")