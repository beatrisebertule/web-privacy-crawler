import json
import sys
import csv
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "crawler_src"))
from crawler import (
    DISCONNECT_SERVICES_PATH,
    listed_categories,
    load_disconnect_categories,
)

OUTDIR = ROOT / "results"

TLD_COUNTRY = {"edu": "us", "nl": "nl", "uk": "uk"}

def country_from_domain(domain):
    tld = domain.lower().rstrip(".").rsplit(".", 1)[-1]
    return TLD_COUNTRY.get(tld, "other")

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

def count_sites_with_category(category, sites):
    """Return the number of sites that contacted a given category"""
    count = 0
    for contacted in sites:
        if category in contacted:
            count += 1
    return count

def session_replay_domains(path):
    """Return the set of domains that are associated"""
    with open(path, encoding="utf-8") as file:
        categories = json.load(file)["categories"]
    domains = set()
    for entities in categories.values():
        for entity in entities:
            for entity_info in entity.values():
                if entity_info.get("session-replay") == "true":
                    for value in entity_info.values():
                        if isinstance(value, list):
                            domains.update(value)
    return domains


def matched_domain(host, domains):
    parts = host.split(".")
    for i in range(len(parts) - 1):
        candidate = ".".join(parts[i:])
        if candidate in domains:
            return candidate
    return None

if __name__ == "__main__":
    sr_domains = session_replay_domains(DISCONNECT_SERVICES_PATH)

    seen_records = {}

    folder_names = ["crawl_data_desktop", "crawl_data_mobile", "crawl_data_block", "crawl_data_ignore"]
    for folder_name in folder_names:
        folder_path = ROOT / folder_name
        if not folder_path.exists():
            print(f"Folder {folder_path} does not exist. Please run the crawler first.")
            sys.exit(1)

        # For each har file, retrieve the website name and the hosts it contacted
        crawl = folder_name.removeprefix("crawl_data_").capitalize()
        for har in folder_path.glob("*.har"):
            website = har.stem
            for host in sent_request_hosts(har):
                match = matched_domain(host, sr_domains)
                if match:
                    seen_records.setdefault((website, match), set()).add(crawl)

    order = ["Desktop", "Mobile", "Block", "Ignore"]

    csv_path = OUTDIR / "09_session_replay.csv"
    OUTDIR.mkdir(exist_ok=True)
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["Website", "Session replay domain", "Country", "Observed crawl(s)"])
        for (website, domain), crawls in sorted(seen_records.items()):
            w.writerow([website, domain,
                        country_from_domain(website).upper(),
                        ", ".join(c for c in order if c in crawls)])
    print(f"Wrote {csv_path} ({len(seen_records)} rows)")
