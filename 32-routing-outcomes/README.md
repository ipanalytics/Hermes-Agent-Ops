# 32 — routing-outcomes

_Russian version: [README.ru.md](README.ru.md)_

![License](https://img.shields.io/github/license/ipanalytics/Hermes-Agent-Ops.svg)
![Status](https://img.shields.io/badge/status-production-green.svg)
![Python](https://img.shields.io/badge/python-3.10+-blue.svg)

Routing outcomes analyzes which models actually handle the jobs based on usage audit logs and job status data.

## Overview

I analyze routing effectiveness by connecting usage audit logs (model, tokens, errors, silence) with current job statuses. My report shows per-model performance metrics and identifies where models are most expensive or failing.

## How it works

I load audit logs from the last 14 days and current job configurations. I aggregate runs, tokens, and errors by model. I track token costs by job and model combination. I identify jobs with non-ok status for failure analysis.

## Quick start

```bash
python3 routing_outcomes.py
```

Set `ROUTING_WINDOW_DAYS` to change the analysis window. Set `AGENT_HOME` to specify the Hermes configuration directory.

## Usage

The script reads from `~/.hermes/cron/usage_audit.jsonl` and `~/.hermes/cron/jobs.json`. It prints a compact report showing model performance and expensive job assignments.

## Outputs

- Per-model summary: runs, token volume, error rates
- Most expensive job-model combinations 
- Jobs not in OK status

## Limitations

Requires audit logs and job configuration files to be accessible. Analysis window is limited to recent data.

## Structure

- `routing_outcomes.py` - Main analysis script
- `tests/test_routing_outcomes.py` - Unit tests
- `examples/` - Sample input data

## License

MIT