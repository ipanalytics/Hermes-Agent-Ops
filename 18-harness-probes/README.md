# 18 — harness-probes

_Русская версия: [README.ru.md](README.ru.md)_

![License](https://img.shields.io/badge/license-Apache%202.0-blue)
![Status](https://img.shields.io/badge/status-active-success)
![Runtime](https://img.shields.io/badge/runtime-python%203.10%2B-informational)
![Dependencies](https://img.shields.io/badge/dependencies-stdlib%20only-lightgrey)

**The acceptance gate for an agent's own scaffolding: deterministic probes, an explicit baseline, and a regression flag on every change.**

I run Hermes — a home AI agent that lives on my server, follows a schedule, and does its own routine: digests, price watches, health monitoring, watchdog-of-watchdogs. Everything around the model itself I call the *harness*: the prompt files, the schedules under `cron` (the system scheduler that fires commands at set times), the guard scripts that enforce budgets, the routing tables that decide which model a job uses, the wrappers that deliver digests. The harness changes every day. A change can quietly break what worked yesterday — and the failure does not look like a crash. The agent still answers chat, the crons still fire, and the regression shows up three days later as a missing digest or a duplicate download. That is the failure mode this folder exists to catch.

## Why it exists

Before I had this gate, a "small refactor" of a guard script cost me a quiet week. The script kept exiting 0; my logger happily recorded nothing; downstream a digest stopped showing one of its sections. I noticed when the human in my household did. The lesson I had to learn twice: the harness has no test suite of its own. Prompts get edited, schedules move, guard scripts get rewritten, routing tables change provider. Each of those is a place where a regression can land, and none of them is the kind of bug that announces itself.

`probes.py` is my attempt to give the harness a small, honest acceptance test. Each probe is a deterministic check against the artifacts the agent is supposed to produce — fresh reports, non-empty spools, parseable state files, guard scripts that stay silent under the cap, digests with a minimum number of items, recent job outputs free of credentials. The first time the suite passes, I freeze the result as a baseline. From that point on, any harness edit is a two-command operation: `run` before the change, `check` after. `check` fails only on a *regression* — a probe that passed in the baseline and fails now. Failures that were already failing are reported but do not block, so a known-broken corner does not paralyse the gate.

## What "probe" means here

A probe is one user-visible promise, written as a JSON entry. There is no code to write to add one — the kinds the runner understands cover most of what I want to verify, and the probe file is just data. The full set lives in `examples/probe_set.example.json`; I copy it into my data directory, point the paths at my own artifacts, edit the values and run `accept` to record it as the baseline.

The kinds shipped today:

| Kind | Checks |
|---|---|
| `file_fresh` | file exists, younger than N hours, at least M bytes |
| `files_no_empty` | no zero-byte files left in a spool directory |
| `json_keys` | JSON parses, required nested keys present, minimum element count |
| `script_silent` / `script` | command exits 0 with empty / non-empty / unconstrained stdout |
| `text_match` | a file contains a regex at least N times (e.g. three cards in a digest) |
| `secrets_clean` | newest N files of a directory contain no credential-shaped strings |

A probe does not look at model output and does not score answer quality. It checks artifacts: the report file was written, the spool is not full of empty files, the state JSON parses and has the right keys, the budget guard did not actually fire, the digest has at least three cards, the last 25 outputs of the cron directory do not contain a `sk-…` token. That is the surface where harness regressions actually show up.

## How it works

The runner is one Python script that takes a mode argument:

| Step | What happens |
|---|---|
| `run` | executes every probe, writes `data/probes_last.json`, prints failures, exits 1 if any |
| `check` | same execution, then diffs against `data/probes_baseline.json`; regressions exit 1 |
| `accept` | records current results as the baseline — a deliberate act, not a side effect |
| `list` | prints the probe set with ids, kinds and titles |

The day-to-day pattern:

```bash
python3 probes.py run      # before the change
python3 probes.py check    # after the change — exit 1 on regression
```

`run` is a snapshot: it shows me the current pass/fail of every probe and exits 1 on any failure. `check` is what I actually want before merging a harness edit: it compares against the frozen baseline and exits 1 only on a regression. A probe that has been failing for a week because I have not gotten around to it will keep printing its failure, but it will not block a clean change elsewhere.

`accept` is the only thing that touches `probes_baseline.json`. I treat it the way I treat a force-push — a deliberate, documented act, not something that happens as a side effect of a successful run. That property matters: a probe set that drifts silently is worse than no probe set at all.

Everything reads its paths relative to `HARNESS_HOME` (default `~/.hermes`), so the same probe set works on a laptop, a VPS, or a container. The wrapper `probes_check.sh` is one line of bash that calls `probes.py check`; I use it from cron so the command is stable even if I rename or wrap things later.

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

The exit code is what the supervisor reads. `0` means healthy, `1` means at least one probe failed (or, under `check`, at least one regression), `2` means the probe set is missing. Healthy hours mean an empty stdout and no delivery — the wrapper is silent when there is nothing to say, and prints the regression only when something changed.

## Why the baseline is a separate file

This is the design choice I care about most. A probe set that drifts silently is worse than no probe set. Keeping the accepted results in `probes_baseline.json`, written only by an explicit `accept`, means the definition of "working" changes on purpose. If I edit a probe and forget to re-accept, my next `check` will rightly call it a regression; if I edit the harness and the probes still pass, that change is admitted by default. The pattern is taken from research on regression-aware skill and harness editing (arXiv 2605.29668: proposed changes are admitted only when a held-out probe set shows no net regression), and running it bears the same conclusion out: the value is not in having tests, it is in refusing a change that trades one green check for another.

The two commands — `run` and `check` — also answer different questions. `run` answers "is my agent working right now?"; `check` answers "did my last change break anything that used to work?". I run `run` when something feels off; I run `check` after every harness edit. Both write to `data/probes_last.json`; only `accept` writes to `probes_baseline.json`.

## Outputs

The runner writes a JSON report at every run, so I can chart it later or feed it to another tool. `data/probes_last.json` looks like:

```json
{
  "checked_at": "2026-09-13T16:55:02",
  "total": 7,
  "passed": 7,
  "probes": [{"id": "report-fresh", "kind": "file_fresh", "ok": true, "why": "2166 б, 2.1 ч назад"}]
}
```

Each probe entry carries its id, its kind, its pass/fail, and a one-line human-readable `why` — e.g. `"старый: 51.4 ч > 30 ч"` or `"совпадений 2 < 3"`. The exit codes: `0` healthy, `1` failure (or regression under `check`), `2` missing probe set. The wrapper returns the same codes, so any supervisor that understands non-zero exits will do.

## Operational notes

These are the rules I learned the hard way. They are not in `probes.py`; they are how I keep `probes.py` honest.

- Probes must be deterministic. A probe whose output contains a timestamp will look changed on every run; put timestamps in the report, not in the checks. I learned this when a "digest is fresh" probe kept regressing every morning — the cause was a clock embedded in the file content, not the file's mtime.
- `secrets_clean` prints the offending file name, never the matched value, so a run log does not become the leak. If the script ever prints `sk-XXXXXXXX…` instead of the filename, that is a bug I need to fix immediately.
- One probe should describe one user-visible promise. When a probe starts failing for a reason I accept permanently, that is a decision — update the probe, then `accept`. I do not let a probe lie for months; lying probes erode trust in the ones that still bite.
- Keep the set small enough to run in under a minute. Slow probes get skipped under pressure, and the moment I am tempted to skip a probe is the moment it would have caught something.
- The probe set is data, not code. Editing `probes.py` is a much bigger decision than editing the JSON; I treat the script as infrastructure and the JSON as configuration.
- When I add a new probe, I write it as failing first, run it, watch it fail for the reason I expect, then either fix the artifact or fix the probe. A probe that passes on the first try is suspicious — usually it tested the wrong thing.

## Scope

In scope: deterministic verification of an agent's own artifacts and guard scripts.
Out of scope: testing the model's answer quality (see folder 21 for measuring what automation lets through), load testing, and application-level unit tests. Probes are about *what the harness promised the world it would produce*, not what the model did with the prompt.

## Use cases

I use this folder for four things, and have used it for others I did not anticipate:

- Cron-driven agents where nobody reviews each run. The probes do the reviewing.
- Guard scripts (budget caps, delivery watchdogs) that must stay silent in the healthy case. A probe that runs the guard and asserts silence catches the case where a refactor accidentally made the guard noisy.
- Multi-host setups where the same harness runs on a VPS and a home machine. The `HARNESS_HOME` switch means one probe file covers both.
- Any pipeline whose failure mode is "the file was not written" rather than "the process crashed". For the "wrong" case, a probe cannot help; I need an evaluation, not a check.

## Limitations

I want to be plain about what this folder does not do.

- Probes verify what someone encoded. They cannot notice a promise nobody wrote down. If a new digest format ships and the old probes still pass, the suite says "everything is fine" while the readers see junk.
- They check artifacts, not intent: a digest with three cards passes even if the cards are wrong topics.
- The baseline is a snapshot; after a deliberate behaviour change, an unaccepted baseline will report a regression that is really a decision. The discipline of `accept` is the only thing standing between me and a baseline that lies.
- A probe can pass while the world is broken, and a probe can fail while nothing is broken. The suite is a guardrail, not a guarantee.

## Directory structure

```
18-harness-probes/
├── probes.py                     # runner: run | check | accept | list
├── probes_check.sh               # cron wrapper (silent when healthy)
├── examples/probe_set.example.json
└── tests/test_probes.py          # offline tests: freshness, regression, secrets, parsing
```

`tests/test_probes.py` is the suite I use to develop `probes.py` itself — it spins up a temporary `HARNESS_HOME` and exercises each probe kind end-to-end without needing the real harness. It catches "did I break freshness detection?" and "did I break regression detection?" before I commit. It is not a substitute for running against a real `$HARNESS_HOME`; it is a sanity check that the runner does what its docstring says.

## Deployment

No dependencies beyond the Python standard library. Run from any scheduler; the wrapper returns the exit code, so any supervisor that understands non-zero exits will do. The whole thing is one script and one JSON file, which is the point: the smallest thing that can sit between a harness edit and production.

## License

Apache 2.0 — see the repository LICENSE.

## Disclaimer

Probes reduce the blast radius of harness edits; they do not make an agent safe to run without oversight. The secret scanner is a heuristic for catching accidents, not a security control. A probe that passes today does not promise the same probe will pass tomorrow; the discipline of `accept` after a deliberate behaviour change is on me, not on the tool.