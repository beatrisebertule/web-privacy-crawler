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
the system libraries Chromium needs. On macOS and Linux the command may be `python3` instead of
`python`.

## Run

From repo root. Chromium opens in a window so the crawl needs a desktop session, not a server
with no display. 

Designed to only run one mode at a time, not several at once, to avoid getting blocked by bot 
or spam protection.

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

Outputs in `crawl_data_<mode>/`, one set of files per site:

```
ru.nl.har
ru.nl_pre_consent.png
ru.nl_post_consent.png     (not in ignore mode)
ru.nl.webm
```

`sites.csv` has a header row, then `domain,country,...` per line.

`services.json` in this folder is a copy of Disconnect's list, downloaded 2026-10-30 from
github.com/disconnectme/disconnect-tracking-protection at commit 5ec90f1b9691. The crawler
doesn't download it at crawl time.

## Resuming

Each finished site is appended to `crawled_<mode>.txt`. Reruns in the same mode will skip sites listed in that file.
To crawl the whole list again, delete that file or move it somewhere else.

## Tests

```
pip install -r requirements-dev.txt
python -m pytest tests
```
