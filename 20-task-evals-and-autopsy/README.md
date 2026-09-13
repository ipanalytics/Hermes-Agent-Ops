# 20 — task-evals-and-autopsy

_Русская версия: [README.ru.md](README.ru.md)_

![License](https://img.shields.io/badge/license-Apache%202.0-blue)
![Status](https://img.shields.io/badge/status-active-success)
![Runtime](https://img.shields.io/badge/runtime-python%203.10%2B-informational)

**"The job ran" is not "the job did its work", and a stack trace is not a diagnosis.**

> A cron that exits 0 and delivers nothing looks exactly like a quiet week. A failure that repeats
> daily looks like noise in the log. This folder covers the middle of the reliability loop: checks
> that verify the *output* a scheduled agent promised, and an autopsy that turns an error string into
> a class and a next step.

## Overview

| Tool | Job |
|---|---|
| `task_evals.py` | output freshness/size/shape, failure streaks, stuck queues — silent when healthy |
| `postmortem.py` | classify the last error, journal it, report each new failure exactly once |
| `briefing.py` | compile open work, recent changes, health counters and unresolved failures into one short brief a job can read |

## How task_evals works

Checks are declared, not coded:

```json
{"id": "digest-cards", "kind": "output_fresh", "jobs": ["job-digest-morning"],
 "max_age_hours": 30, "min_bytes": 2000,
 "pattern": "^\\s*(?:№\\s*\\d+|\\d+)[).]?\\s", "min_hits": 3}
```

`output_fresh` is the useful one: the newest output of a job must be recent, non-trivial in size and
contain the structural marks of its promise — three numbered cards in a digest, a heading in a
report. `no_failures` watches streaks rather than single errors, because one failure is a coincidence
and three is a pattern. `queue_clear` runs your own queue command and counts stuck items.

Exit code 0 with no output means the jobs did what they promised; the scheduled run is read by a
human only when it speaks.

## How postmortem works

Five classes, first match wins: delivery, model limit, state/database, network, script. Each carries
advice, so the report is a next step rather than a restatement:

```
🩺 Разбор падений (автоматически):
  • стриминг-новинки [состояние/база]: session storage could not be written
    → проверить место и блокировки базы, затем health-check рантайма
```

Fingerprints of reported failures are stored, so a problem that has been seen is not repeated every
run — the journal keeps the history, the report keeps only what is new. This is the difference
between an alert stream people mute and one they read.

## How briefing works

Scheduled agents start with an empty head. Reconstructing context by re-reading everything costs the
same tokens on every run; compiling it once into a short brief costs a few hundred and is read by
many. The brief pulls open work items, the tail of a change log, health counters from the other
tools in this series, and unresolved failures — then writes it where a job reads it as context.

## Quick start

```bash
cp examples/task_evals.json .
python3 task_evals.py --jobs ~/.hermes/cron/jobs.json --output-dir ~/.hermes/cron/output \
    --config examples/task_evals.json --report ~/.hermes/data/task_evals.json
python3 postmortem.py --jobs ~/.hermes/cron/jobs.json
python3 briefing.py --config examples/briefing.json
```

## Limitations

- Structural checks verify shape, not meaning: three cards can still be the wrong three things.
- Classifiers are lexical; an unusual error lands in "прочее" and is reported as unclassified, which
  is the honest outcome.
- The briefing is only as current as the files it reads; a stale source produces a stale brief.

## Directory structure

```
20-task-evals-and-autopsy/
├── task_evals.py             # did the work happen: freshness, size, shape, streaks, queues
├── postmortem.py             # error → class → advice, each new failure once
├── briefing.py               # one short brief compiled from local state
├── examples/{task_evals,briefing}.json
└── tests/test_autopsy.py
```

## License

Apache 2.0 — see the repository LICENSE.

## Disclaimer

The classifier covers the failure modes of one real deployment; extend the class list before
trusting it on another.
