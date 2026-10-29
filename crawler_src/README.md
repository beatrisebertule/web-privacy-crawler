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
