import json
import sys
from pathlib import Path
from urllib.parse import urlsplit

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "crawler_src"))
from crawler import (
    DISCONNECT_SERVICES_PATH,
    listed_categories,
    load_disconnect_categories,
)
from plot_text import CRAWL_AXIS_LABEL

OUTDIR = ROOT / "results"

def sent_request_hosts(har):
    """Return the set of hostnames a page sent requests to"""
    with open(har, encoding="utf-8") as f:
        har = json.load(f)

        hosts = set()
        for entry in har["log"]["entries"]:
            if entry["response"]["status"] <= 0: # If the request was blocked, skip it
                continue
            hostname = urlsplit(entry["request"]["url"]).hostname
            if hostname:
                hosts.add(hostname)
    return hosts

def contacted_disconnect_categories(har, categories_by_host):
    """Return the set of Disconnect categories the website sent at least one request to"""
    contacted = set()
    hosts = sent_request_hosts(har)
    for host in hosts:
        contacted |= listed_categories(host, categories_by_host)
    return contacted

def plot(counts, category, exercise):
    """Plot a bar chart of the number of sites that contacted a given category"""
    fig, ax = plt.subplots(figsize=(6, 4))
 
    bars = ax.bar(counts.keys(), counts.values(), color=["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728"])
    ax.bar_label(bars)
    ax.margins(y=0.1)
 
    ax.set_title(f"Crawl Comparison ({exercise})")
    ax.set_xlabel(CRAWL_AXIS_LABEL)
    ax.set_ylabel(f"# sites with {category.lower()}")
    ax.grid(axis="y", alpha=0.4)
    ax.set_axisbelow(True)

    out = OUTDIR / f"03_crawl_comparison_{category}.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)

def categories_of_crawl(folder, categories_by_host):
    """Return a list with all the contacted categories per website in a crawl"""
    categories = []
    for har in folder.glob("*.har"):
        categories.append(contacted_disconnect_categories(har, categories_by_host))
    return categories

def count_sites_with_category(category, sites):
    """Return the number of sites that contacted a given category"""
    count = 0
    for contacted in sites:
        if category in contacted:
            count += 1
    return count

if __name__ == "__main__":
    categories_by_host = load_disconnect_categories(DISCONNECT_SERVICES_PATH)

    desktop_categories = categories_of_crawl(ROOT / "crawl_data_desktop", categories_by_host)
    mobile_categories = categories_of_crawl(ROOT / "crawl_data_mobile", categories_by_host)
    blocked_categories = categories_of_crawl(ROOT / "crawl_data_block", categories_by_host)
    ignored_categories = categories_of_crawl(ROOT / "crawl_data_ignore", categories_by_host)

    advertising_counts = {
        "Desktop": count_sites_with_category("Advertising", desktop_categories),
        "Mobile": count_sites_with_category("Advertising", mobile_categories),
        "Block": count_sites_with_category("Advertising", blocked_categories),
        "Ignore": count_sites_with_category("Advertising", ignored_categories),
    }

    analytics_counts = {
        "Desktop": count_sites_with_category("Analytics", desktop_categories),
        "Mobile": count_sites_with_category("Analytics", mobile_categories),
        "Block": count_sites_with_category("Analytics", blocked_categories),
        "Ignore": count_sites_with_category("Analytics", ignored_categories),
    }

    plot(advertising_counts, "advertising", "3a")
    plot(analytics_counts, "analytics", "3b")
    
    print(f"\nWrote {OUTDIR}/03_crawl_comparison_advertising.png")
    print(f"Wrote {OUTDIR}/03_crawl_comparison_analytics.png")