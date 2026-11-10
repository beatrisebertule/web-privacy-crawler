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
 
    ax.set_title(f"Location Comparison ({exercise}) - Crawl-Ignore")
    ax.set_xlabel("Website Country") 
    ax.set_ylabel(f"# sites with {category.lower()}")
    ax.grid(axis="y", alpha=0.4)
    ax.set_axisbelow(True)

    out = OUTDIR / f"location_comparison_{category}.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)

def categories_of_crawl(folder, categories_by_host, pattern):
    """Return a list with all the contacted categories per website in a crawl"""
    categories = []
    for har in folder.glob(pattern):
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

    ignore_dir = ROOT / "crawl_data_ignore"
    nl_categories = categories_of_crawl(ignore_dir, categories_by_host, "*.nl.har")
    uk_categories = categories_of_crawl(ignore_dir, categories_by_host, "*.uk.har")
    us_categories = categories_of_crawl(ignore_dir, categories_by_host, "*.edu.har")
    print("sites per country:", len(nl_categories), len(uk_categories), len(us_categories))

    advertising_counts = {
        "NL": count_sites_with_category("Advertising", nl_categories),
        "UK": count_sites_with_category("Advertising", uk_categories),
        "US": count_sites_with_category("Advertising", us_categories),
    }

    analytics_counts = {
        "NL": count_sites_with_category("Analytics", nl_categories),
        "UK": count_sites_with_category("Analytics", uk_categories),
        "US": count_sites_with_category("Analytics", us_categories),
    }

    plot(advertising_counts, "advertising", "5a")
    plot(analytics_counts, "analytics", "5b")
