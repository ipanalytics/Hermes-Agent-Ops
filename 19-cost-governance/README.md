# 19 — cost-governance

_Русская версия: [README.ru.md](README.ru.md)_

![License](https://img.shields.io/badge/license-Apache%202.0-blue)
![Status](https://img.shields.io/badge/status-active-success)
![Runtime](https://img.shields.io/badge/runtime-python%203.10%2B-informational)

**A budget cap that acts, and a cost metric that counts finished work instead of tokens.**

Alerts assume somebody is awake. A job on a schedule burns money at 04:00 as happily as at noon,
and "requests" is not a unit a budget can actually be spent against. This folder closes that gap
with three small tools: a cap that pauses the most expensive scheduled jobs, a report of dollars
per *successful* task per role, and a static check that keeps a job's allowed tool list from
silently shrinking the capability the prompt relies on.

## The slot in the series

Module 01 (`agent-wallet-guard`) is the alarm — it sees the provider balance move. Module 10
(`cost-dashboard`) is the map — it shows *where* the spend went. Neither one **does** anything to
the spend. This folder is the teeth: a daily token cap that pauses the worst offenders, and two
companion tools that keep the cap honest and the agent's toolkit honest. Module 22
(`difficulty-router`) consumes `cost_per_outcome`'s number to decide which jobs are worth a more
expensive model — that link is what makes "cost per outcome" a knob instead of a number.

## Overview

| Tool | Job |
|---|---|
| `budget_guard.py` | sums today's tokens from the usage ledger; over the cap, pauses the N most expensive jobs and releases them on `--resume` |
| `cost_per_outcome.py` | joins ledger + job list + price map, reports dollars per successful run per role |
| `toolsets_audit.py` | flags jobs whose prompt mentions a tool the job's toolset does not allow |

## How budget_guard works

The usage ledger is JSONL — one record per model call with `ts`, `job_id`, `prompt_tokens`,
`completion_tokens`, an optional `error`. The guard sums the current UTC day, compares the total
with `cap_tokens_per_day`, and when the cap is exceeded it sorts jobs by spend and pauses the top
N by running a shell command template:

```json
{
  "cap_tokens_per_day": 12000000,
  "top_n": 3,
  "pause_command": "hermes cron pause {job_id}",
  "resume_command": "hermes cron resume {job_id}"
}
```

The templates are arbitrary — point them at any scheduler CLI. The point of the cap is not the
threshold; the point is that the cap **acts**, in the dark, without me being at the keyboard.

Three properties matter more than the threshold itself:

- **No cascade.** The guard records the day it acted on (`action_date` in its own state file) and
  refuses to pause anything else on that same UTC day. Pausing the top three, then on the next
  hourly check the next three, then the next three, is how a budget guard turns into a full
  outage — every important job paused, no alarm raised because the cron is silent when there is
  nothing to do. The cap is meant to soften the day, not end it.
- **Only its own decisions are reversible.** `--resume` releases exactly the jobs this guard
  paused; it never releases a job a human paused on purpose. The set of paused job ids lives in
  the guard's own state file, separated from the scheduler's state, so the two systems cannot
  step on each other.
- **Silence when healthy.** When the day is under the cap, the script exits 0 with empty output.
  A supervisor can treat an empty run as success — no heartbeat needed, no "all clear" line to
  parse.

```bash
python3 budget_guard.py --dry-run     # print the plan, touch nothing
python3 budget_guard.py --resume      # release what this guard paused
```

`--dry-run` is the one to run first on a new deployment. It walks the same code path, prints which
jobs would be paused and the exact `pause_command` for each, and writes nothing. I keep it wired
into a weekly cron that just spits the dry-run into the morning digest — if I ever see a long
list there at 07:00, the cap is wrong, not the day's traffic.

## How cost_per_outcome works

A price list answers "what does a token cost". A budget is spent against what a finished piece of
work cost. Those are different numbers, and the difference is what makes model swaps hard to
evaluate.

The tool joins three files: the JSONL usage ledger, the job list (so each call is mapped back to a
named scheduled task), and a price map keyed by model name. Jobs are bucketed into *roles* by
regex over the job's name, so the report follows my naming instead of imposing a fixed taxonomy:

```
cost per successful task (last 7 days)
  mail                  ok   28/  28  $1.15  →  $0.041 per success
  media                 ok   34/  41  $1.86  →  $0.055 per success
  infra                 ok   96/  99  $0.90  →  $0.009 per success
  TOTAL                 ok  158          $3.91  →  $0.025 per success
```

The denominator is **successful** runs; the numerator is **all** the spend, including the
unsuccessful calls. A failed call is paid for too, so it has to stay in the numerator; but it
shouldn't claim it produced a result. That asymmetry is the whole point: a model that is cheaper
per token can still lose per task if it fails more often, and this number makes that visible. I
caught one swap that way — a mid-tier model was half the per-token price of the incumbent, but
the failure rate went from 1/41 to 1/12 and the per-success number rose instead of falling.

Watching the number across a week shows which change actually paid off. Per-token prices lie;
per-success prices don't.

## How toolsets_audit works

An agent runtime lets the scheduled job's tool list be restricted to a known subset. That shortens
the fixed prompt prefix on every single turn — real savings, because a long tool catalogue is
read into the prompt whether or not the job uses it. The failure mode is silent: prune the wrong
toolset and the job keeps running while the capability it needed quietly disappears. No error,
just a tool call that never happens, and a job that completes with empty results.

This tool reads the job list and a `toolset → regex` map (in `examples/toolset_map.json`) and
reports every prompt that references a tool the job cannot use:

```
possible missing toolsets: 1
  job-media-clip: нет «file», а в промпте — «read_file»
```

That single line once caught a typo (`files` instead of `file`) that had been quietly disabling
file access on a media job for weeks — no error, just the missing capability. It is the cheapest
audit in this folder, runs in well under a second, and earns its place on the same cron that
refreshes the job list.

## Quick start

```bash
cp examples/budget_guard.json   ~/.hermes/data/budget_guard.json
cp examples/prices.json         .
cp examples/toolset_map.json    .

python3 toolsets_audit.py --jobs ~/.hermes/cron/jobs.json \
                          --map  examples/toolset_map.json

python3 cost_per_outcome.py --jobs   ~/.hermes/cron/jobs.json \
                            --audit  ~/.hermes/cron/usage_audit.jsonl \
                            --prices examples/prices.json \
                            --window-days 7

python3 budget_guard.py --dry-run     # first: see what would happen
python3 budget_guard.py               # then: act if the cap is exceeded
```

I run `toolsets_audit.py` on every save of `jobs.json` — the cost is microseconds and the failure
mode it catches is the kind that goes unnoticed for a month. `cost_per_outcome.py` runs on a 7-day
window weekly and lands in the same digest as the wallet guard and the dashboard, so the three
reports are read together: alert (a wall-clock signal), dashboard (a breakdown), cost-per-outcome
(a per-task signal). `budget_guard.py` runs hourly; it is the only one that mutates state.

## Limitations

- Token accounting is only as good as the ledger the runtime writes. A wrapped or retried call
  that is recorded once instead of twice will understate the day; a call that is recorded twice
  will trip the cap for no real spend. I keep a separate sanity check on the ledger's daily sum
  against the wallet guard's balance delta; if they disagree by more than a few percent, one of
  them is wrong.
- The guard pauses jobs, it does not reschedule them. Pair it with an early-morning `--resume`
  or with a `--resume` step at the start of the next-day cron, or the day's pause carries into
  the next day's morning traffic.
- Cost per outcome rewards cheap tasks with many runs. A job that fires hourly and is allowed
  to be sloppy will dominate the table. Always read the number *per role*, never as one global
  score; the average hides the role where the swap actually paid off.
- `toolsets_audit` is lexical: it finds mentions in the prompt text, not actual tool calls. A
  prompt that *mentions* a tool but does not call it will still trigger; that is a false
  positive worth a manual look, not an automatic fix.

## Directory structure

```
19-cost-governance/
├── budget_guard.py           # cap with pause/resume, once per UTC day, own state
├── cost_per_outcome.py       # dollars per successful task per role
├── toolsets_audit.py         # prompt text vs. allowed tools
├── examples/
│   ├── budget_guard.json     # cap, top_n, pause/resume templates
│   ├── prices.json           # per-model input/output rates + role regexes
│   └── toolset_map.json      # toolset name → mention-in-prompt regex
└── tests/test_cost_governance.py   # cap arithmetic, top-N, pause/resume idempotence, toolset matching
```

## License

Apache 2.0 — see the repository `LICENSE`.

## Disclaimer

Pausing scheduled work is an operational decision with real consequences. Run `--dry-run` on a new
deployment before letting the guard act, and pair the guard with a `--resume` step so a quiet
pause doesn't carry into the next day.