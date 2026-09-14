# 25 — Querylog Domain Scout

_Russian version: [README.ru.md](README.ru.md)_

![License](https://img.shields.io/github/license/ipanalytics/Hermes-Agent-Ops)
![Status](https://img.shields.io/badge/status-active-brightgreen)
![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue)

This module analyzes AdGuard Home querylog to identify which domains each device requests. It maintains a database of seen domain-client pairs and generates reports on newly observed domains.

## Overview

The Querylog Domain Scout extracts domain request data from AdGuard Home's querylog.json, processes it to identify new domain requests by client device, and maintains a SQLite database of all observed domain-client pairs. It helps track which domains your devices are accessing and identifies new domains that appear over time.

## How it works

The module connects to an AdGuard Home instance via SSH to retrieve the querylog.json file. It parses the log entries to extract client IP, requested domain, timestamp, and blocked status. After filtering out technical noise domains, it updates a local SQLite database with new domain-client pairs. The module can operate in two modes: baseline (process entire log) or tick (process only recent entries).

## Quick start

```bash
# Set environment variables
export ADGUARD_HOST="your-adguard-server"
export SSH_KEY_PATH="~/.ssh/adguard_key"
export DATABASE_PATH="./ag_scout.db"

# Run baseline collection (first time)
python3 ag_domain_scout.py --mode baseline

# Run incremental update
python3 ag_domain_scout.py --mode tick

# Generate report of new domains in last 7 days
python3 ag_domain_scout.py
```

## Usage

```bash
python3 ag_domain_scout.py [options]

Options:
  --mode MODE          Mode: 'baseline' (full log) or 'tick' (recent entries) [default: tick]
  --days N             Report on domains newer than N days [default: 7]
  --tail-bytes N       Size of log tail to read in 'tick' mode [default: 8000000]
  --no-ingest          Show report only, don't update database
  --quiet              Quiet mode for cron jobs
  --alerts             Show only blocking problems
```

## Outputs

- Database file with domain-client pairs and timestamps
- Console report of new domains organized by client
- Blocking effectiveness status for added rules

## Limitations

- Requires SSH access to AdGuard Home server
- Depends on querylog.json format remaining consistent
- May require adjustment of CLIENTS mapping for accurate device identification

## Structure

```
ag_domain_scout.py     # Main script
README.md              # English documentation
README.ru.md           # Russian documentation
tests/test_domain_scout.py  # Unit tests
examples/              # Sample data
```

## License

MIT