import csv
import json
from pathlib import Path
from urllib.parse import urlsplit
 
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from tld import get_fld

from final_page import final_page_host

ROOT = Path(__file__).resolve().parent.parent
OUTDIR = ROOT / "results"
TRANCO_PATH = ROOT / "tranco.csv" # Tranco list, one "rank,domain" per line
TLD_COUNTRY = {"edu": "US", "nl": "NL", "uk": "UK"} # top-level domain -> country of the university

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

def load_tranco_ranks(tranco):
    "Return a ictionary with the Tranco rank of each domain"
    ranks = {}
    with open(tranco, encoding="utf-8") as f:
        for row in csv.reader(f):
            if len(row) < 2 or not row[0].isdigit(): # skip header line or empty lines
                continue
            ranks[row[1].strip().lower()] = int(row[0])
    return ranks

def domains_per_site(folder):
    """Return a list of (website, number of distinct third-party domains) for every website in a crawl"""
    sites = []
    for har in folder.glob("*.har"):
        website = har.stem.split("_")[0]
        sites.append((website, len(third_party_domains(har))))
    return sites

def country_of(website):
    """Return the country of a website based on its top-level domain (e.g. 'ru.nl' -> 'NL')"""
    TLD = website.split(".")[-1]
    return TLD_COUNTRY.get(TLD, "NA")

def make_table_rows(sites, ranks):
    """Return a list of the rows of the table"""
    rows = []
    for website, no_domains in sites:
        rows.append((website, ranks.get(website, "NA"), country_of(website), no_domains))
    return rows
 
def plot(rows, name, arrow):
    """Plot a table of websites with their Tranco rank, country and number of third-party domains"""
    fig, ax = plt.subplots(figsize=(8, 2))
    ax.axis("off")
 
    table = ax.table(
        cellText=rows,
        colLabels=["Website", "Tranco rank", "Country", f"Number of distinct third-party domains {arrow}"],
        cellLoc="center",
        loc="center",
    )

    for col in range(4):
        table[0, col].set_text_props(weight="bold")
 
    out = OUTDIR / f"{name}.png"
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)

def number_of_domains(site):
    """Return the number of third-party domains of a (website, no_domains) pair, used to sort the websites"""
    return site[1]
 
if __name__ == "__main__":
    ranks = load_tranco_ranks(TRANCO_PATH)
    sites = sorted(domains_per_site(ROOT / "crawl_data_desktop"))

    highest = sorted(sites, key=number_of_domains, reverse=True)[:3] # (a) Top 3 websites with highest distinct 3rd party domain requests
    lowest = sorted(sites, key=number_of_domains)[:3] # (b) Top 3 websites with lowest distinct 3rd party domain requests
 
    plot(make_table_rows(highest, ranks), "most_third_party_domains_desktop", "↓")
    plot(make_table_rows(lowest, ranks), "fewest_third_party_domains_desktop", "↑")