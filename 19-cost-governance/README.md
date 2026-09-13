# 19 — cost-governance

_Русская версия: [README.ru.md](README.ru.md)_

![License](https://img.shields.io/badge/license-Apache%202.0-blue)
![Status](https://img.shields.io/badge/status-active-success)
![Runtime](https://img.shields.io/badge/runtime-python%203.10%2B-informational)

**A budget cap that acts, and a cost metric that counts finished work instead of tokens.**

> Alerts assume somebody is awake. A scheduled agent burns money at 04:00 as happily as at noon, and
> "requests" is not a unit a budget can be spent against. These three tools close that gap: a cap
> that pauses the most expensive jobs, a report of dollars per *successful* task per role, and a
> static check that keeps an agent's tool prefixes from silently growing back.

## Overview

| Tool | Job |
|---|---|
| `budget_guard.py` | sums today's tokens from a usage ledger; over the cap it pauses the N most expensive jobs and releases them on `--resume` |
| `cost_per_outcome.py` | joins ledger + job list + price map, reports cost per successful run per role |
| `toolsets_audit.py` | flags jobs whose prompt mentions a tool their toolset does not allow |

## How budget_guard works

The ledger is JSONL — one record per model call with `ts`, `job_id`, `prompt_tokens`,
`completion_tokens`, optional `error`. The guard sums the current UTC day, compares with
`cap_tokens_per_day`, and when the cap is exceeded sorts jobs by spend and pauses the top N by
running a command template:

```json
{"cap_tokens_per_day": 12000000, "top_n": 3,
 "pause_command": "hermes cron pause {job_id}",
 "resume_command": "hermes cron resume {job_id}"}
```

Three properties matter more than the threshold:

- **No cascade.** It acts once per day (`action_date` in its own state). Pausing the top three and
  then, on the next hourly check, the next three, is how a budget guard turns into an outage.
- **Only its own decisions are reversible.** `--resume` releases the jobs this tool paused, never a
  job a human paused for a reason.
- **Silence when healthy.** No output means under the cap; a supervisor can treat an empty run as
  success.

```bash
python3 budget_guard.py --dry-run     # print the plan, touch nothing
python3 budget_guard.py --resume      # release what it paused
```

## How cost_per_outcome works

A price list answers what a token costs; a budget is spent against what a finished piece of work
costs. Failures are paid for, so they stay in the numerator and are excluded from the denominator:

```
media   ok 34/41  $1.86  →  $0.055 per success
mail    ok 28/28  $1.15  →  $0.041 per success
infra   ok 96/99  $0.90  →  $0.009 per success
```

The roles are regexes over job names, so the report follows your naming, not a fixed taxonomy.
Watching this number across a week tells you which change actually paid off — a model swap cheaper
per token can still lose per task if it fails more often.

## How toolsets_audit works

Restricting a job's tool list shortens the fixed prefix on every turn — real savings, and a silent
failure mode when the pruned tool was load-bearing. The check reads the job list and a
toolset→regex map and reports each prompt that references a tool the job cannot use. I found a
typo this way (`files` instead of `file`) that had been quietly disabling file access on a job for
weeks — no error, just a capability that was not there.

## Quick start

```bash
cp examples/budget_guard.json ~/.hermes/data/budget_guard.json
cp examples/prices.json .
python3 toolsets_audit.py --jobs ~/.hermes/cron/jobs.json --map examples/toolset_map.json
python3 cost_per_outcome.py --jobs ~/.hermes/cron/jobs.json \
    --audit ~/.hermes/cron/usage_audit.jsonl --prices examples/prices.json --window-days 7
```

## Limitations

- Token accounting is as good as the ledger your runtime writes; wrapped or retried calls must be
  recorded individually or the daily sum drifts.
- The guard pauses jobs, it does not reschedule them; pair it with an early-morning resume.
- Cost per outcome rewards cheap tasks with many runs; read it per role, not as one global score.
- `toolsets_audit` is lexical: it finds mentions, not real usage.

## Directory structure

```
19-cost-governance/
├── budget_guard.py           # cap with pause/resume, once per day, own state
├── cost_per_outcome.py       # $ per successful task per role
├── toolsets_audit.py         # prompt vs. allowed tools
├── examples/{budget_guard,prices,toolset_map}.json
└── tests/test_cost_governance.py
```

## License

Apache 2.0 — see the repository LICENSE.

## Disclaimer

Pausing scheduled work is an operational decision with real consequences; run `--dry-run` on a new
deployment before letting the guard act.
