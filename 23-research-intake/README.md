# 23 — research-intake

_Русская версия: [README.ru.md](README.ru.md)_

![License](https://img.shields.io/badge/license-Apache%202.0-blue)
![Status](https://img.shields.io/badge/status-active-success)
![Runtime](https://img.shields.io/badge/runtime-python%203.10%2B-informational)

**Read the literature as a corpus you count, not as a feed you scroll — and keep a journal of what you
actually adopted.**

> Most "trend" reports compare what an index chose to show this week with what it chose last week: a
> different sample every time, dressed as a direction. This folder takes the other route — harvest a
> set over a harvesting protocol, count terms locally in equal windows, and keep every idea that
> survives a week in a journal with a first step, a metric and a kill date.

## Overview

| File | Job |
|---|---|
| `oai_harvest.py` | walk an OAI-PMH set with a resumption token, append JSONL, count terms offline |
| `direction_digest.py` | equal-window shares per term, marked only when a shift survives the comparison |
| `backlog.md` | the journal schema and the rules that keep it from becoming a museum |

## Why OAI-PMH and local counting

A search API answers "what does the index think is relevant", one page at a time, subject to rate
limits that have nothing to do with your usage pattern. I measured it directly: the arXiv query API
returned rate-limit errors even for a trivial one-term query, from two different networks — so the
limiting was not per-IP and not fixable by rotating egress. The harvesting protocol has the opposite
design: `ListRecords` with a set and a resumption token walks a whole set, one request at a time, and
the arXiv OAI endpoint served thousands of records per week when the query API would not answer.

Counting then happens locally, over the harvested text, with the regexes you control:

```bash
python3 oai_harvest.py --set cs:cs.AI --days 7 --out data/cs.AI.jsonl
python3 oai_harvest.py --count data/cs.AI.jsonl --terms examples/terms.json
```

That is what makes week-over-week comparison honest: same corpus shape, same patterns, no ranking
changes underneath. Shares travel with the record count, because a week with twice the records
inflates every absolute number.

## The journal

`backlog.md` documents the schema I keep beside the corpus: `status` in
candidate / trying / adopted / rejected, a `first_step` small enough to do this week, a `metric`, a
`kill_by` date, and a mandatory `reason` for rejections. Two of those rules do the heavy lifting:

- **Equal windows, shares not absolutes** — otherwise a busy week reads as a trend.
- **Rejections keep their reason** — "tried it, the metric did not move" is the most reusable line in
  the file, and the only thing that stops the same idea from returning every quarter.

## Quick start

```bash
cp examples/terms.json .
python3 oai_harvest.py --fixture examples/oai_fixture.xml --out data/example.jsonl   # offline check
python3 oai_harvest.py --set cs:cs.AI --days 7 --out data/cs.AI.jsonl
python3 oai_harvest.py --count data/cs.AI.jsonl --terms examples/terms.json
python3 direction_digest.py --corpus data/cs.AI.jsonl --terms examples/terms.json --weeks 5 --out digest.md
```

## Limitations

- Sets overlap and records are re-announced; dedup by identifier handles the common case, not every
  cross-listing.
- Term counting measures vocabulary, not quality: a term can grow because more papers use the word in
  their abstracts.
- OAI-PMH is polite by design: a full set walk takes minutes and several requests. That is the price
  of a stable corpus, and it is cheap at one run a week.

## Directory structure

```
23-research-intake/
├── oai_harvest.py                # ListRecords walk, JSONL, offline counting
├── direction_digest.py           # equal-window shares
├── backlog.md                    # journal schema + rules
├── examples/{terms.json,oai_fixture.xml}
└── tests/test_intake.py          # fixture parsing, counting, windows
```

## License

Apache 2.0 — see the repository LICENSE.

## Disclaimer

Respect the endpoint's terms and rate expectations: one request at a time, a descriptive user agent,
no scraping beyond the protocol.
