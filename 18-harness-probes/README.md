# 18 — harness-probes

_Русская версия: [README.ru.md](README.ru.md)_

![License](https://img.shields.io/badge/license-Apache%202.0-blue)
![Status](https://img.shields.io/badge/status-active-success)
![Runtime](https://img.shields.io/badge/runtime-python%203.10%2B-informational)
![Dependencies](https://img.shields.io/badge/dependencies-stdlib%20only-lightgrey)

**An agent's scaffolding changes every day, and nothing tells you when a change quietly breaks
what worked yesterday.**

> Schedules move, prompts get edited, guard scripts get refactored, routing tables get rewritten.
> Most of that surface has no test suite: the agent still answers, the crons still fire, and a
> regression shows up three days later as a missing digest or a duplicate download. This folder
> is the missing acceptance gate.

## Overview

`probes.py` runs a set of deterministic checks — declared in JSON, no code required — against
the artifacts your agent is supposed to produce: fresh reports, non-empty spools, parseable state
files, guard scripts that stay silent under the cap, digests with a minimum number of items, job
outputs free of credentials. Each run writes a JSON report. The first accepted run becomes the
baseline.

After that, a harness edit is a two-command operation:

```bash
python3 probes.py run      # before the change
python3 probes.py check    # after the change — exit 1 on regression
```

`check` fails only on a *regression*: a probe that passed in the baseline and fails now. Failures
that were already failing are reported but do not block, so a known-broken corner does not
paralyse the gate.

## How it works

| Step | What happens |
|---|---|
| `run` | executes every probe, writes `data/probes_last.json`, prints failures, exits 1 if any |
| `check` | same execution, then diffs against `data/probes_baseline.json`; regressions exit 1 |
| `accept` | records current results as the baseline — a deliberate act, not a side effect |
| `list` | prints the probe set with ids, kinds and titles |

Probe kinds shipped today:

| Kind | Checks |
|---|---|
| `file_fresh` | file exists, younger than N hours, at least M bytes |
| `files_no_empty` | no zero-byte files left in a spool directory |
| `json_keys` | JSON parses, required nested keys present, minimum element count |
| `script_silent` / `script` | command exits 0 with empty / non-empty / unconstrained stdout |
| `text_match` | a file contains a pattern at least N times (e.g. three cards in a digest) |
| `secrets_clean` | newest N files of a directory contain no credential-shaped strings |

Everything reads its paths relative to `HARNESS_HOME` (default `~/.hermes`), so the same probe set
works on a laptop, a VPS, or a container.

## Quick start

```bash
git clone <this repo> && cd 18-harness-probes
export HARNESS_HOME=$HOME/.hermes
cp examples/probe_set.example.json "$HARNESS_HOME/data/probe_set.json"
$EDITOR "$HARNESS_HOME/data/probe_set.json"       # point paths at your artifacts
python3 probes.py run
python3 probes.py accept                           # freeze the good state
```

Wire it into the scheduler as a watchdog — hourly is usually enough:

```cron
55 * * * * /path/to/probes_check.sh   # silent when healthy; prints the regression when not
```

## Why the baseline is a separate file

A probe set that drifts silently is worse than no probe set. Keeping the accepted results in
`probes_baseline.json`, written only by an explicit `accept`, means the definition of "working"
changes on purpose. The pattern is taken from research on regression-aware skill and harness
editing (arXiv 2605.29668: proposed changes are admitted only when a held-out probe set shows no
net regression), with the same conclusion I reached running it: the value is not in having
tests, it is in refusing a change that trades one green check for another.

## Outputs

`data/probes_last.json`:

```json
{
  "checked_at": "2026-09-13T16:55:02",
  "total": 7,
  "passed": 7,
  "probes": [{"id": "report-fresh", "kind": "file_fresh", "ok": true, "why": "2166 б, 2.1 ч назад"}]
}
```

Exit codes: `0` healthy, `1` failure (or regression under `check`), `2` missing probe set.

## Operational notes

- Probes must be deterministic. A probe whose output contains a timestamp will look changed on
  every run; put timestamps in the report, not in the checks.
- `secrets_clean` prints the offending file name, never the matched value, so a run log does not
  become the leak.
- One probe should describe one user-visible promise. When a probe starts failing for a reason you
  accept permanently, that is a decision — update the probe, then `accept`.
- Keep the set small enough to run in under a minute; slow probes get skipped under pressure.

## Scope

In scope: deterministic verification of an agent's own artifacts and guard scripts.
Out of scope: testing the model's answer quality (see folder 21 for measuring what automation
lets through), load testing, and application-level unit tests.

## Use cases

- Cron-driven agents where nobody reviews each run.
- Guard scripts (budget caps, delivery watchdogs) that must stay silent in the healthy case.
- Multi-host setups where the same harness runs on a VPS and a home machine.
- Any pipeline whose failure mode is "the file was not written" rather than "the process crashed".

## Limitations

- Probes verify what someone encoded. They cannot notice a promise nobody wrote down.
- They check artifacts, not intent: a digest with three cards passes even if the cards are wrong
  topics.
- The baseline is a snapshot; after a deliberate behaviour change, an unaccepted baseline will
  report a regression that is really a decision.

## Directory structure

```
18-harness-probes/
├── probes.py                     # runner: run | check | accept | list
├── probes_check.sh               # cron wrapper (silent when healthy)
├── examples/probe_set.example.json
└── tests/test_probes.py          # offline tests: freshness, regression, secrets, parsing
```

## Deployment

No dependencies beyond the Python standard library. Run from the scheduler of your choice; the
wrapper returns the exit code, so any supervisor that understands non-zero exits will do.

## License

Apache 2.0 — see the repository LICENSE.

## Disclaimer

Probes reduce the blast radius of harness edits; they do not make an agent safe to run without
oversight. The secret scanner is a heuristic for catching accidents, not a security control.
