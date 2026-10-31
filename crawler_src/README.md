# Crawler

Playwright crawler for the NWI-IMC074 web privacy measurement. Visits each homepage in a fresh
Chromium context, handles the consent dialog, scrolls, and records a HAR, two screenshots and a
video per site.

## Install

Python 3.12 or newer.

```
pip install -r requirements.txt
python -m playwright install chromium
```

## Run

From the repo root. One mode per run, one browser at a time.

```
python crawler_src/crawler.py -m desktop -l sites.csv
python crawler_src/crawler.py -m mobile  -l sites.csv
python crawler_src/crawler.py -m block   -l sites.csv
python crawler_src/crawler.py -m ignore  -l sites.csv
```

| Mode | Browser | Blocking | Consent |
|---|---|---|---|
| `desktop` | Chromium, desktop | none | accept |
| `mobile` | Chromium emulating Pixel 10 | none | accept |
| `block` | Chromium, desktop | Disconnect blocklist | accept |
| `ignore` | Chromium, desktop | none | no interaction |

Per visit: page load, wait 10 s, accept consent (not in `ignore`), wait 5 s, scroll down, wait
5 s, close.

Output lands in `crawl_data_<mode>/`, one set of files per site:

```
ru.nl.har
ru.nl_pre_consent.png
ru.nl_post_consent.png     (not in ignore mode)
ru.nl.webm
```

`sites.csv` has a header row, then `domain,country,...` per line. Consent button phrases come
from `accept_words.txt` and are tried in file order.

## Tracker blocking

The `block` crawl blocks a request when its hostname is listed in Disconnect's `services.json`
under Advertising, Analytics, Social, FingerprintingInvasive or FingerprintingGeneral, or is a
subdomain of a listed hostname. `stats.g.doubleclick.net` is blocked, `doubleclick.net` is
listed. `adservice.google.com` is blocked, it is listed itself. `www.google.com` is not.

Matching is on the hostname, not on eTLD+1. Of the 3,555 hostnames in those categories, 278
are subdomains and their eTLD+1 is not listed: `adservice.google.com` without `google.com`,
`ads.yahoo.com` without `yahoo.com`. Matching on the request's eTLD+1 would miss those 278.

**NOTE:** One limitation is that a subdomain Disconnect has not listed is not blocked, even when another subdomain
of the same eTLD+1 is. `a.klaviyo.com` is listed and blocked. `b.klaviyo.com` is not listed
and gets through. The analysis counts third parties by eTLD+1 (as per assignment requirements) for the
"domain". A request like that still counts as third party there.

`services.json` in this folder is a copy of Disconnect's list, downloaded 2026-10-30 from
github.com/disconnectme/disconnect-tracking-protection at commit 5ec90f1b9691. No download
at crawl time.

A blocked request is still in the HAR, with status -1 and `_failureText`
`net::ERR_BLOCKED_BY_CLIENT`. The analysis drops it like any request with no response.

## Resuming

Each finished site is appended to `crawled_<mode>.txt`. A rerun of the same mode skips those.
Delete the file to crawl everything again.

## Tests

The tests run the crawler against small HTML pages served from `tests/fixtures/` on localhost,
in a headless browser with all waits set to zero. No real site is contacted.

```
pip install -r requirements-dev.txt
python -m pytest tests
```

Tests marked `xfail` are requirements the crawler does not meet yet. Each one's `reason` says
what is missing. When a fix lands, the test starts passing and pytest reports the stale `xfail`
marker as a failure, so remove the marker with the fix.
