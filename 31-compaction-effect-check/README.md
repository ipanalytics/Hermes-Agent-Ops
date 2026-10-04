# 31 — Compaction Effect Check

_Russian version: [README.ru.md](README.ru.md)_

![License](https://img.shields.io/github/license/ipanalytics/Hermes-Agent-Ops)
![Status](https://img.shields.io/badge/status-active-brightgreen)
![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue)

I changed how the agent compacts its context — a new threshold, a different compaction model, a smaller
tail — and I wanted to know whether it had helped. The honest answer needs two windows of real traffic, one
before the change and one after. This folder is the measurement I use, so "it feels lighter since the change" is
never my evidence.

## Why it exists

Compaction is the easiest place in an agent to make a change that looks like an improvement and costs
money. A compaction model that is three times cheaper per token but fires twice as often is not cheaper. A
lower threshold frees context sooner and quietly bills me on every following turn, because the cached
prefix no longer matches. And a compaction triggered only at the wall leaves the biggest sessions — the
ones with the most to gain — untouched, because they never get a clean moment to compact in.

None of that is visible in the moment. It shows up in the cost curve a week later, which is why the change
has to be measured against its own before-and-after windows instead of judged by how the session felt
afterwards.

## How it works

1. Before the change, the script collects a baseline over a configurable number of days: daily cost, how
   much of it is compaction, and the cache-to-input ratio.
2. I record the exact timestamp of the change. There is no way to reconstruct it later, which is why it
   is a required input rather than a guess.
3. After the observation window, the same numbers are collected again.
4. The script compares them and prints a verdict: cheaper, more expensive, or inside the noise.

Progress is kept in a small state file, so the script can be scheduled and will stay silent until the
observation window has actually passed — a check that reports on itself every day is a check I stop
reading.

## Quick start

```bash
export CHANGE_TIMESTAMP=$(date +%s)   # when the new policy went live
export COMPACT_MODEL_NAME="glm-5.3-flash"
export BASELINE_DAYS=3
export OBSERVE_DAYS=3

python3 compaction_effect_check.py
```

## Usage

Everything is configured through the environment:

- `HERMES_DB_PATH` — the usage database (default `~/.hermes/state.db`)
- `COMPACT_STATE_FILE` — the experiment state file (default `~/.hermes/data/compaction_experiment.json`)
- `BASELINE_DAYS` / `OBSERVE_DAYS` — window lengths in days (default 3 / 3)
- `COMPACT_MODEL_NAME` — the model that does the compacting, used to attribute its share of the spend
  (default `glm-5.3-flash`)
- `CHANGE_TIMESTAMP` — Unix timestamp of the policy change

Run it repeatedly (a daily cron is the natural place); it prints once, when there is something to say.

## Outputs

- daily cost, before against after;
- the compaction model's own cost and call count;
- the cache-to-input token ratio — the column where a "cheaper" policy usually turns out not to be;
- a verdict, in plain words, on whether the change is worth keeping.

## Limitations

- It reads a usage database. If the deployment does not record per-model usage, there is nothing to
  compare.
- Both windows have to contain a normal mix of traffic. A baseline that covers a weekend is not a
  baseline.
- Attribution is by model-name pattern, so two policies that use the same compaction model cannot be told
  apart — change one thing at a time.
- The experiment assumes a single change inside the observation window. A second change during it
  invalidates the result, and the script cannot tell me that I made one.

## Structure

```
├── compaction_effect_check.py  # main script
├── README.md                   # English documentation
├── README.ru.md                # Russian documentation
├── tests/
│   └── test_compaction_effect_check.py
└── examples/
    ├── sample_config.env       # example environment variables
    └── experiment_state.json   # example state file
```

## Related

- **35-context-compaction-engine** — the engine this check exists to accept: compaction by working state,
  judged by whether the task can still be continued.
- **03-agent-ops-playbook** — the incident that turned context size from an annoyance into an operational
  topic.

## License

MIT License - see the LICENSE file in the repository for details.
