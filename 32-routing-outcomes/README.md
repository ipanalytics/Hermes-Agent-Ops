# 32 — Routing Outcomes

_Russian version: [README.ru.md](README.ru.md)_

![License](https://img.shields.io/github/license/ipanalytics/Hermes-Agent-Ops.svg)
![Status](https://img.shields.io/badge/status-production-green.svg)
![Python](https://img.shields.io/badge/python-3.10+-blue.svg)

A job that had not produced a digest in three days was running on a model that had started timing
out every night at four in the morning, and the only signal I had was the missing message in my
chat. The model was cheap, the cron was
silent, and the bill for the dead runs kept accumulating. This folder checks the assignment
against the deployment's own records: which models really finish their jobs, which ones burn
tokens, and which jobs are failing right now.

## What "routing" means here

In Hermes, every scheduled job — a price watch, a digest, a health check, anything on cron —
runs against one specific language model. I picked the model when I created the job, and that
choice lives in `jobs.json`: the list of jobs, each with an id, a name, the assigned model, an
enabled flag, and a last_status field written by the agent after each run. Picking a model is
the cheapest place to cut a bill, so it is also the place where the cut hurts when it is wrong.

The agent also writes an audit log: one JSON record per model call, with the timestamp, the
model, the job id, total tokens spent, whether the call errored, and whether the model came back
silent (returned an empty reply — a separate failure mode from an error). The audit log is the
ground truth for "which model really did this run and what it cost." Both files are on disk
already; the script in this folder reads them and prints the comparison.

## Why it exists

"Put a cheaper model on this job" is a decision about money, not taste: if the model does not
finish the job, a failure at four in the morning goes unnoticed and the tokens are already
spent. There is nothing to argue with until the numbers exist — "model X seems fine" is an
opinion, and the opinion was wrong twice on me. The audit log and the job statuses are already
on disk, and they are enough to produce error rates and token spend per job.

The other reason it exists is the asymmetry of failures. A model that succeeds but slowly will
make my digests late, and I will notice; a model that silently times out at 4 a.m. will not be
noticed for days, because the cron entry was supposed to be silent. The audit log catches the
silent cases — `error: false, response_silent: true` — and they show up in the report as a
separate counter. The combination of "errors" and "silence" is what makes the report honest.

## How it works

1. The script reads `~/.hermes/cron/usage_audit.jsonl` — the audit log for the last 14 days —
   and `~/.hermes/cron/jobs.json` with the current job configurations.
2. Runs, tokens and errors are aggregated per model, so each model gets its own error rate and
   token volume. The script also tracks "silent" runs (empty reply, no error) separately from
   errors, because a silent run is a different failure mode.
3. Token spend is tracked per job-and-model pair, so the costliest assignments stand out
   immediately. A job that mostly uses one model but occasionally has another — say a fallback
   when the primary times out — shows up here as two rows for the same job, and the dominant
   model is the candidate to fix or replace.
4. Enabled jobs whose `last_status` is not `ok` are listed — those are the ones I start with.
   A disabled job that is failing is not interesting; an enabled job that is failing is the
   thing to look at first.

The window defaults to 14 days. Two weeks is long enough to catch a failure pattern that only
shows up on certain days (end-of-month reports, weekend traffic dips, weekly digests), and short
enough that the report reflects the current assignment rather than the assignment as it looked
six months ago. I keep the window configurable through `ROUTING_WINDOW_DAYS`; the test suite
overrides it.

## Quick start

```bash
python3 routing_outcomes.py
```

The analysis window is 14 days; I change it with `ROUTING_WINDOW_DAYS`, and I point `AGENT_HOME`
at the Hermes configuration directory. The default paths are `~/.hermes/cron/usage_audit.jsonl`
and `~/.hermes/cron/jobs.json` — the same two files the agent writes, so the script reads what
the deployment produces, with no separate database to maintain.

When there is no audit data inside the window (a fresh deployment, a purged log), the script
prints "Routing: no audit data in window." and exits 0 — silence is the honest answer when
there is nothing to count. The script never crashes on missing files; it tells me it has
nothing and waits for next week.

## Outputs

The report is four sections, in this order:

- a per-model summary: runs, token volume, error rate, sorted by tokens so the expensive
  models are at the top;
- the most expensive job-and-model pairs: for each job, which model is doing most of the
  tokens, and what the configuration currently assigns (so I can see when the actual model
  differs from the assigned one, usually because a fallback kicked in);
- jobs that are not in OK status, with their `last_status` from `jobs.json` — these are the
  jobs I start with, because "the report says a model fails" is less actionable than "this
  named job is currently broken".

The script prints to stdout. There is no JSON output, no CSV, no machine-readable file: the
report is meant to be read, and the columns line up with terminal width. I usually pipe it
into `less` or paste the interesting section into a note.

## Limitations

The module reads rather than guesses: without the audit log and the job configuration files it
has nothing to count. The window is short — recent data only: it shows the current picture,
not what the assignment looked like six months ago. A model that was good last year and bad
this month will appear bad; a model that was bad last year and fixed itself will appear good.
That is what the window is for.

Other things the report does not try to do:

- it does not score model quality, only reliability and cost;
- it does not suggest a cheaper replacement, only flags the jobs whose current assignment is
  the costliest;
- it does not call out jobs whose token spend went up between runs unless the increase is
  large enough to land at the top of the per-model list.

I keep those out on purpose. The report's job is to put the four numbers next to each other
(runs, tokens, errors, silence) and let me decide; suggestions and quality scores would add
opinion to a measurement, and the measurement is what I trust.

## Structure

```
24-llm-to-script/
├── routing_outcomes.py                # main analysis script
├── tests/test_routing_outcomes.py     # unit tests
└── examples/                          # sample input data
    ├── jobs.json
    └── usage_audit.jsonl
```

`routing_outcomes.py` is 95 lines and runs on Python 3.10+. It uses only `collections`,
`json`, `os`, `datetime`, `pathlib` — all standard library. The example jobs and audit lines
in `examples/` are tiny but realistic: three jobs with different statuses, three audit lines
covering success, error, and silent response. The tests in `tests/test_routing_outcomes.py`
cover the three shapes the input can take (list of jobs, dict with `jobs` key, empty audit),
and they mock `AGENT_HOME` so they run with no real files in place.

## License

MIT