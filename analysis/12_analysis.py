import json
import sys
import csv
from pathlib import Path
from urllib.parse import urlsplit

from tld import get_fld

import dns.resolver
import dns.exception

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "crawler_src"))
from crawler import (
    DISCONNECT_SERVICES_PATH,
    listed_categories,
    load_disconnect_categories,
)

ENTITIES = "./entities.json"       # disconnect entities list (for metric d)

OUTDIR = ROOT / "results"


def sent_request_hosts(har):
    """Return the set of hostnames a page sent requests to"""
    with open(har, encoding="utf-8") as f:
        har = json.load(f)

        hosts = set()
        for entry in har["log"]["entries"]:
            # Skip request if it seems blocked
            if entry["response"]["status"] <= 0:
                continue
            hostname = urlsplit(entry["request"]["url"]).hostname
            if hostname:
                hosts.add(hostname)
    return hosts

def get_cname(host):
    """Return the CNAME record for a given hostname"""
    try:
        answer = dns.resolver.resolve(host, "CNAME", lifetime=5)
    except dns.exception.DNSException:
        return None
    target = answer[0].target.to_text().rstrip(".")
    print(f"CNAME for {host} → {target}")
    return target

def fld(host):
    """eTLD+1 for a bare hostname or URL; '' if it can't be parsed."""
    if not host:
        return ""
    host = host.strip().lower().rstrip(".")
    if _is_ip(host):
        return host
    return get_fld(host, fix_protocol=True, fail_silently=True) or ""

def _is_ip(host):
    """Return True if the host is an IPv4 or IPv6 address"""
    p = host.split(".")
    return len(p) == 4 and all(x.isdigit() for x in p)

def load_entity_map(path):
    """Load a map of domains to entity names from the Disconnect file"""
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    ents = data.get("entities", data)
    dmap = {}
    for name, obj in ents.items():
        for domain in list(obj.get("resources", [])) + list(obj.get("properties", [])):
            key = fld(domain)
            if key:
                dmap.setdefault(key, name)
    return dmap

if __name__ == "__main__":
    sr_domains = load_disconnect_categories(DISCONNECT_SERVICES_PATH)

    dmap = load_entity_map(ENTITIES)
    cnames = {} 

    folder_names = ["crawl_data_desktop", "crawl_data_mobile", "crawl_data_block", "crawl_data_ignore"]

    # For each har file in the folder, get the website name and the hosts it contacted
    for folder_name in folder_names:
        found = set()
        folder_path = ROOT / folder_name
        crawl = folder_name.removeprefix("crawl_data_").capitalize()
        for har in folder_path.glob("*.har"):
            website = har.stem
            site_fld = fld(website)

            # For each host, check if has a corresponding CNAME record
            for host in sent_request_hosts(har):

                # If the host is not a subdomain of the website, skip
                if fld(host) != site_fld:
                    continue
                if host not in cnames:
                    cnames[host] = get_cname(host)
                target = cnames[host]
                if target != None and fld(target) != site_fld and listed_categories(target, sr_domains):
                    found.add((website, host, target))

        # create a seperate CSV file for the current crawl with the found CNAME records
        curr_crawl = folder_name.removeprefix("crawl_data_")
        csv_path = OUTDIR / f"12_cname_cloaking_{curr_crawl}.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["First-party subdomain", "CNAME record", "CNAME entity", "Disconnect categories"])
            for (website, host, target) in sorted(found):
                w.writerow([host,
                            target,
                            dmap.get(fld(target), "unknown"),
                            ", ".join(sorted(listed_categories(target, sr_domains)))])
        print(f"Wrote {csv_path} ({len(found)} rows)")
