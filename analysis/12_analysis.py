import json
import sys
import csv
import ipaddress
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
from final_page import final_page_host
from first_party_responses import first_party_responses

ENTITIES = ROOT / "crawler_src" / "entities.json"  # Disconnect entities list

OUTDIR = ROOT / "results"

# Assignment says to follow CNAME chains. This caps one that never ends.
MAX_CHAIN_LENGTH = 16


def sent_request_hosts(har, website):
    """Return the set of first-party hostnames a page sent requests to"""
    hosts = set()
    for entry in first_party_responses(har, website):
        hosts.add(urlsplit(entry["request"]["url"]).hostname)
    return hosts

def get_cname(host):
    """Return the CNAME record for a given hostname"""
    try:
        answer = dns.resolver.resolve(host, "CNAME", lifetime=5)
    # No CNAME and no such name are answers. Timeouts go up to the caller.
    except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
        return None
    target = answer[0].target.to_text().rstrip(".")
    print(f"CNAME for {host} → {target}")
    return target

def get_cname_chain(host):
    """Return every CNAME target of a hostname, in order"""
    chain = []
    target = get_cname(host)
    while target is not None and target != host and target not in chain and len(chain) < MAX_CHAIN_LENGTH:
        chain.append(target)
        target = get_cname(target)
    return chain

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
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True

def load_entity_map(path):
    """Load a map of domains to entity names from the Disconnect file"""
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    ents = data.get("entities", data)
    dmap = {}
    for name, obj in ents.items():
        for domain in list(obj.get("resources", [])) + list(obj.get("properties", [])):
            # Whole listed name, since `tld` treats names like cloudfront.net as a suffix
            key = domain.strip().lower()
            if key:
                dmap.setdefault(key, name)
    return dmap

def entity_of(host, dmap):
    """Return the entity owning a hostname or its closest listed parent, or NA"""
    labels = host.lower().split(".")
    for first_label in range(len(labels)):
        name = dmap.get(".".join(labels[first_label:]))
        if name:
            return name
    return "NA"

if __name__ == "__main__":
    # Piped stdout on Windows defaults to cp1252. It can't print the arrow.
    sys.stdout.reconfigure(encoding="utf-8")
    sr_domains = load_disconnect_categories(DISCONNECT_SERVICES_PATH)

    dmap = load_entity_map(ENTITIES)
    cnames = {}

    folder_names = ["crawl_data_desktop", "crawl_data_mobile", "crawl_data_block", "crawl_data_ignore"]

    # A missing crawl would otherwise give a CSV with no rows that looks like a real result.
    for folder_name in folder_names:
        if not any((ROOT / folder_name).glob("*.har")):
            sys.exit(f"No HAR files in {ROOT / folder_name}")
    OUTDIR.mkdir(parents=True, exist_ok=True)
    lookups_failed = False

    # For each har file in the folder, get the website name and the hosts it contacted
    for folder_name in folder_names:
        found = set()
        failed_hosts = set()
        folder_path = ROOT / folder_name
        crawl = folder_name.removeprefix("crawl_data_").capitalize()
        for har in folder_path.glob("*.har"):
            website = har.stem
            with open(har, encoding="utf-8") as f:
                har_data = json.load(f)
            # First party is the page after redirects, not the file name
            site_fld = fld(final_page_host(har_data, website))

            # For each host, check if has a corresponding CNAME record
            for host in sent_request_hosts(har_data, website):

                # If the host is not a subdomain of the website, skip
                if fld(host) != site_fld:
                    continue
                if host not in cnames:
                    try:
                        cnames[host] = get_cname_chain(host)
                    except dns.exception.DNSException as error:
                        print(f"CNAME lookup failed for {host}: {type(error).__name__}")
                        failed_hosts.add(host)
                        continue
                # First name in the chain that Disconnect lists and that isn't on the site's own domain
                target = next(
                    (hop for hop in cnames[host] if fld(hop) != site_fld and listed_categories(hop, sr_domains)),
                    None,
                )
                if target != None:
                    found.add((website, host, target))

        # Skip the CSV. A table missing hosts would look complete.
        if failed_hosts:
            print(f"No CSV for {crawl}: {len(failed_hosts)} lookups failed")
            lookups_failed = True
            continue

        # create a seperate CSV file for the current crawl with the found CNAME records
        curr_crawl = folder_name.removeprefix("crawl_data_")
        csv_path = OUTDIR / f"12_cname_cloaking_{curr_crawl}.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh, lineterminator="\n")
            w.writerow(["First-party subdomain", "CNAME record", "CNAME entity", "Disconnect categories"])
            for (website, host, target) in sorted(found):
                w.writerow([host,
                            target,
                            entity_of(target, dmap),
                            ", ".join(sorted(listed_categories(target, sr_domains)))])
        print(f"Wrote {csv_path} ({len(found)} rows)")

    if lookups_failed:
        sys.exit("Some CNAME lookups failed. Rerun to retry them")
