# 25 — ransomware-monitor

_Русская версия: [README.ru.md](README.ru.md)_

![License](https://img.shields.io/badge/License-MIT%20%2B%20CC--BY--4.0-blue.svg)
![Status](https://img.shields.io/badge/Status-active-success.svg)
![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB.svg)

A feed watcher that tells me only what is new. It reads the public ransomware report feed,
keeps a state file of everything already seen, matches each item against the regions I care
about, and prints nothing when there is nothing new.

## Overview

Ransomware leak feeds are noisy in a specific way: the same incident is republished, the
description is a wall of HTML, and there is no region field. I want two things from such a
feed — a delta and a region — and neither is in the payload.

The monitor keeps a state file with the last seen timestamp and up to 2000 identifiers, so a
cron job can run it every 30 minutes and stay silent for days. Region matching goes over city
and company-name vocabulary for DE/AT/CH/RU/US, because a two-letter code appears in ordinary
words: `(DE)` counts, `deal` does not.

## How it works

1. Fetch the RSS feed with a browser user agent and a 45-second timeout, three attempts.
2. Parse items with the standard library (no feedparser, no requests).
3. Drop everything older than the last run; keep the rest in the state file.
4. For each new item, extract the group and victim from the title, strip HTML from the
   description, and look for a region token or a known city name.
5. Print up to 25 new items with Berlin-local timestamps in a fixed width block — nothing at
   all when the delta is empty.

## Quick start

```bash
export RANSOM_RSS="https://www.ransomware.live/rss"      # feed URL
export RANSOM_STATE="~/.hermes/data/ransom_rss_state.json"
python3 ransom_rss.py
```

Cron example (every 30 minutes, silent by design):

```
*/30 * * * * RANSOM_STATE=~/.hermes/data/ransom_rss_state.json python3 ~/.hermes/scripts/ransom_rss.py
```

## Usage

```
python3 ransom_rss.py            # delta since the last run
python3 ransom_rss.py --help     # usage and environment variables
```

## Outputs

```
2026-09-08 12:10 (Europe/Berlin)  de  Heilbronn
lockbit3 -> Example GmbH
  Description: manufacturer, production stopped, 40 GB claimed
  https://www.ransomware.live/id/...
```

## Limitations

- Region matching is vocabulary based: a company named after a city elsewhere still lands in
  the wrong bucket. The token list is in the script and meant to be edited.
- The feed is a public aggregator; it republishes claims from leak sites, which are not
  verified incidents. Treat the output as a lead, not as reporting.
- A first run on an empty state reports the whole current feed window. Seeding the state file
  before the first cron tick avoids a wall of old items.

## Structure

```
25-ransomware-monitor/
├── ransom_rss.py                 # the monitor (standard library only)
├── tests/test_ransomware_monitor.py
├── examples/feed_sample.xml
└── README.md, README.ru.md
```

## License

MIT + CC-BY-4.0, see the repository LICENSE.
