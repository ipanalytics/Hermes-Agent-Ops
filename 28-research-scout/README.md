# 28 — research-scout

_Russian version: [README.ru.md](README.ru.md)_

![License](https://img.shields.io/github/license/ipanalytics/Hermes-Agent-Ops)
![Status](https://img.shields.io/badge/status-production-green)
![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue)

Research Scout monitors fresh arXiv papers via OAI-PMH, filters by themes relevant to agentic systems, and scores by community reception. I run this as a cron job to catch new research directions before they become mainstream.

## Overview

I collect fresh papers from arXiv CS categories using OAI-PMH protocol, filter by regex patterns matching my interests (agent harness, evals, memory, routing), and rank by both thematic relevance and Hugging Face daily paper votes. Results go to a markdown file for review and model processing.

## How it works

The script runs in two modes: collection (slow) and cache reuse (fast). In collection mode, I fetch recent papers via OAI-PMH, score them by theme matches (title hits worth 3x abstract), deduplicate against seen papers, and save top picks. Cache mode returns cached results if under 30 minutes old.

## Quick start

```bash
python3 research_scout.py
```

Configure window days, cache timeout, and theme patterns via constants in the script. Set up as a cron job to run periodically.

## Usage

The script outputs a stable fingerprint string to stdout for cron gate monitoring. Fresh papers appear in `~/.hermes/data/research_scout.md`. Papers are deduplicated by ID and kept in `~/.hermes/data/research_scout_seen.json`.

## Outputs

- `~/.hermes/data/research_scout.md`: ranked papers with abstracts and scores
- `~/.hermes/data/research_scout_seen.json`: deduplication journal
- `~/.hermes/data/research_scout_cache.json`: caching mechanism
- stdout: stable fingerprint for cron gate

## Limitations

Relies on arXiv OAI-PMH availability and Hugging Face daily paper votes. Theme filtering is regex-based and may miss nuanced topics. Only covers CS categories currently.

## Structure

```
research_scout.py     # Main script
README.md            # This file
README.ru.md         # Russian translation
tests/test_research_scout.py   # Tests
examples/            # Sample inputs
```

## License

MIT