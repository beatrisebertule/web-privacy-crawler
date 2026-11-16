# Crawler

Playwright crawler for Online Tracking & Privacy (NWI-IMC074) group assignment. Visits each homepage in a fresh
Chromium context, handles consent dialogs, scrolls, and records a HAR, two screenshots and video per site.

## Install

Python 3.11 or newer. From repo root, in a fresh virtual environment:

```
python -m venv .venv
.venv\Scripts\activate          (Windows)
source .venv/bin/activate       (macOS, Linux)
pip install -r requirements.txt
python -m playwright install chromium
```

On Linux, use `python -m playwright install --with-deps chromium` instead. It also installs
the system libraries Chromium needs. On macOS and Linux the command may be `python3`.

`requirements.txt` pins Playwright to 1.64.1 because each Playwright version comes with its own
Chromium build and its own device list, this will keep it consistent for all group members.

## Run

From repo root. Chromium opens in a window, so
the crawl needs a desktop session, not a bare server (one mode per run, one browser at a time).

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

Outputs in `crawl_data_<mode>/`, one set of files per site:

```
ru.nl.har
ru.nl_pre_consent.png
ru.nl_post_consent.png     (not in ignore mode)
ru.nl.webm
```

`sites.csv` has a header row, then `domain,country,...` per line. Consent button phrases come
from `accept_words.txt`.

## Tracker blocking

The `block` crawl blocks a request when its hostname is listed in Disconnect's `services.json`
under Advertising, Analytics, Social, FingerprintingInvasive, or FingerprintingGeneral (or is a
subdomain of a listed hostname). `stats.g.doubleclick.net` is blocked because `doubleclick.net`
is listed. `adservice.google.com` is blocked because it's listed itself. `www.google.com` is not.

Matching is on hostname, not on eTLD+1. For the listed hostnames, some are subdomains and their eTLD+1 is not included: `adservice.google.com` without `google.com`,
`ads.yahoo.com` without `yahoo.com`. Trying to match eTLD+1 would fail to catch those.

**NOTE:** One limitation is that a subdomain that Disconnect has not listed is not blocked, even when another subdomain
of the same eTLD+1 is. `a.klaviyo.com` is listed and blocked. `b.klaviyo.com` is not listed
and gets through. The analysis counts third parties by eTLD+1 (as per assignment requirements) for the
"domain". A request like that still counts as third party.

`services.json` in this folder is a copy of Disconnect's list, downloaded 2026-10-30 from
github.com/disconnectme/disconnect-tracking-protection at commit 5ec90f1b9691. The crawler
doesn't download it at crawl time.

A blocked request is still in the HAR, with status -1 and `_failureText`
`net::ERR_BLOCKED_BY_CLIENT`. Analysis drops it just like any other request with no response.

## Resuming

Each finished site is appended to `crawled_<mode>.txt`. Reruns in the same mode will skip sites listed in that file.
If you want to crawl the entire list again, delete the file entirely or move your previous copy somewhere else.

## Tests

The tests run the crawler against small HTML pages served from `tests/fixtures/` on localhost,
in a headless browser with all waits set to zero. No real site is contacted.

```
pip install -r requirements-dev.txt
python -m pytest tests
```

Tests marked `xfail` are requirements the crawler does not meet yet. Each one's `reason` says
what requirement/feature is missing. When that criteria is met, the test starts will pass and pytest reports the stale `xfail`
marker as a failure, making it easy to notice and remove the marker.
