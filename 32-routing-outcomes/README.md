# 32 — Routing Outcomes

_Russian version: [README.ru.md](README.ru.md)_

![License](https://img.shields.io/github/license/ipanalytics/Hermes-Agent-Ops.svg)
![Status](https://img.shields.io/badge/status-production-green.svg)
![Python](https://img.shields.io/badge/python-3.10+-blue.svg)

I assign cron jobs to models once, and after that the assignment is usually trusted rather than
checked. This folder checks it against the deployment's own records: which models really finish their
jobs, which ones burn tokens, and which jobs are failing right now.

## Why it exists

"Put a cheaper model on this job" is a decision about money, not taste: if the model does not finish
the job, a failure at four in the morning goes unnoticed and the tokens are already spent. There is
nothing to argue with until the numbers exist — "model X seems fine" is an opinion. The audit log and
the job statuses are already on disk, and they are enough to produce error rates and token spend per
job.

## How it works

1. The script reads `~/.hermes/cron/usage_audit.jsonl` — the audit log for the last 14 days — and
   `~/.hermes/cron/jobs.json` with the current job configurations.
2. Runs, tokens and errors are aggregated per model, so each model gets its own error rate and token
   volume.
3. Token spend is tracked per job-and-model pair, so the costliest assignments stand out immediately.
4. Enabled jobs whose `last_status` is not `ok` are listed — those are the ones I start with.

## Quick start

```bash
python3 routing_outcomes.py
```

The analysis window is 14 days; I change it with `ROUTING_WINDOW_DAYS`, and I point `AGENT_HOME` at the
Hermes configuration directory.

## Outputs

- per-model summary: runs, token volume, error rate;
- the most expensive job-and-model pairs;
- jobs that are not in OK status.

## Limitations

The module reads rather than guesses: without the audit log and the job configuration files it has
nothing to count. The window is short — recent data only: it shows the current picture, not what the
assignment looked like six months ago.

## Structure

- `routing_outcomes.py` — the main analysis script;
- `tests/test_routing_outcomes.py` — unit tests;
- `examples/` — sample input data.

## License

MIT
