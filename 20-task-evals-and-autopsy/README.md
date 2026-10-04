# 20 — task-evals-and-autopsy

_Русская версия: [README.ru.md](README.ru.md)_

![License](https://img.shields.io/badge/license-Apache%202.0-blue)
![Status](https://img.shields.io/badge/status-active-success)
![Runtime](https://img.shields.io/badge/runtime-python%203.10%2B-informational)

**"The job ran" is not "the job did its work", and a stack trace is not a diagnosis.**

A cron that exits 0 and delivers nothing looks exactly like a quiet week. A failure that repeats
daily looks like noise in the log. This folder covers the middle of the reliability loop: checks
that verify the *output* a scheduled agent promised, and an autopsy that turns an error string
into a class and a next step.

## The slot in the series

Module 05 (`cron-of-crons`) is the orchestrator — it knows what runs and when. Module 18
(`harness-probes`) is the editor-side twin of this folder: probes that gate a code change by
checking the harness. This folder is the runtime twin of the same idea: every scheduled run
itself is checked against the *promise* it made, and the result is a brief that goes back into
the next run's context so the agent doesn't have to remember. Module 18 checks the code; this
folder checks the work.

## Overview

| Tool | Job |
|---|---|
| `task_evals.py` | output freshness/size/shape, stuck queues, and failure streaks — silent when healthy |
| `postmortem.py` | classify the last error, journal it, report each new failure exactly once |
| `briefing.py` | compile open work, recent changes, health counters and unresolved failures into one short brief a job can read |

## How task_evals works

Checks are declared, not coded. A small JSON config lists every check the agent should pass, and
the kind of check it is:

```json
{
  "id": "digest-cards",
  "kind": "output_fresh",
  "jobs": ["job-digest-morning"],
  "max_age_hours": 30,
  "min_bytes": 2000,
  "pattern": "^\\s*(?:№\\s*\\d+|\\d+)[).]?\\s",
  "min_hits": 3
}
```

Three check kinds ship today, and they cover the failure modes I have actually hit:

- **`output_fresh`** is the one that matters. A job's newest output must be recent (younger than
  `max_age_hours`), non-trivial in size (bigger than `min_bytes`), and contain the structural marks
  of its promise — three numbered cards in a morning digest, a heading in a report, the right
  prefix in a release file. The `pattern` is a regex; `min_hits` is how many times it must match.
  This is the check that catches the silent empty digest: the cron exited 0, the file is newer
  than yesterday, but it is 600 bytes of "no items today" and the real digest never went out.
- **`no_failures`** watches streaks rather than single errors. One failure is a coincidence; three
  in a row is a pattern. The job list already records `failure_streak`; this check raises a problem
  when the streak crosses the configured `max_streak` (default 2). Catching a streak at three
  instead of thirty is the difference between a fixable bug and a silent quarterly regression.
- **`queue_clear`** runs a queue command (e.g. `your-queue-cli --list`) and counts items that match
  `stale_pattern` (default `\\bstale\\b`). More than `max_recent_stale` and it raises. This is the
  check for jobs that pull from a queue I own, where the queue can grow stale in the background
  while the cron happily exits 0.

The output of every run is a JSON report (`--report`, default `task_evals.json`) plus a one-line
stdout summary on a failure. Exit code 0 with empty stdout means the jobs did what they promised;
the scheduled run is read by a human only when it speaks.

## How postmortem works

Five classes, first match wins. Each carries an advice line so the report is a next step rather
than a restatement of the error:

| Class | Example match | Advice |
|---|---|---|
| доставка (delivery) | `chat not found`, `sendMessage`, `thread` | check the target and the bot's permissions on that chat/topic |
| лимит модели (model limit) | `rate limit`, `429`, `quota` | spread over time, change upstream, or wait for the window |
| состояние/база (state/db) | `session storage`, `database is locked`, `wal` | check disk and locks, then runtime health-check |
| сеть (network) | `timeout`, `connection reset`, `SSL` | retry once; on repeat, check route/proxy |
| скрипт (script) | `Traceback`, `SyntaxError`, `exit code [1-9]` | read the last line of the trace; retry is pointless |

The classifier is **lexical** — it matches against the error string the runtime records against
the job. That is deliberate: I want an answer in milliseconds without a model call, and I want it
to be reproducible. An unusual error falls through to `прочее` and is reported as unclassified;
that is the honest outcome, not a fake match.

```
🩺 Разбор падений (автоматически):
  • стриминг-новинки [состояние/база]: session storage could not be written
    → проверить место и блокировки базы, затем health-check рантайма
```

The crucial bit is **deduplication**. Every failure is hashed (`job_id` + first 160 chars of the
error), and the hash is stored in `--seen` (default `postmortem_seen.json`). A problem that has
already been reported is *not* reported again on the next run; the journal keeps the history, the
report keeps only what is new. This is the difference between an alert stream people mute and one
people read: a known problem lives in the journal, a new problem lands in the morning digest
exactly once.

## How briefing works

Scheduled agents start with an empty head: no memory of what was decided yesterday, what broke,
or what is waiting on a human. Rebuilding that context by re-reading everything costs the same
tokens on every run, whether the agent uses the result or not. Compiling it once into a short
brief costs a few hundred tokens and is read by many jobs.

The brief pulls four sections from local files, configured in `examples/briefing.json`:

- **Open work** — items from a backlog file with statuses like `candidate` / `trying` / `adopted`.
  A `next_step` field is included so the agent knows what is being asked of it.
- **Recent changes** — the tail of a `CHANGELOG.md` (or any log-shaped file), limited to N lines.
  The agent can see what changed since the last time it was awake.
- **Health** — counters from sibling tools. Each `health_files.<name>` entry is a JSON file with a
  `problems` array; the brief reports the count next to the name. When `task_evals.json` says
  `проблем 2`, the agent sees that before it starts.
- **Unresolved failures** — the first five jobs with a non-empty `last_error` from the job list.

The brief is written to `out_path` (default `~/.hermes/data/briefing.md`) and also printed to
stdout. A scheduler that wants to inject it as the job's own context can capture stdout and store
it; a scheduler that wants it on disk reads `out_path`. The brief is plain markdown so a job can
either summarise it further or use it verbatim.

## Quick start

```bash
cp examples/task_evals.json  .
cp examples/briefing.json    .

python3 task_evals.py --jobs       ~/.hermes/cron/jobs.json \
                     --output-dir  ~/.hermes/cron/output \
                     --config      examples/task_evals.json \
                     --report      ~/.hermes/data/task_evals.json

python3 postmortem.py --jobs     ~/.hermes/cron/jobs.json \
                      --journal  ~/.hermes/data/postmortems.md \
                      --seen     ~/.hermes/data/postmortem_seen.json

python3 briefing.py --config examples/briefing.json
```

I run `task_evals.py` after every scheduled batch (the supervisor cron calls it as the last
stage); `postmortem.py` runs hourly so a brand-new failure appears in the digest on the same day;
`briefing.py` runs at the start of every cron and writes to a path the job's prompt template
includes as fixed context.

## Limitations

- Structural checks verify shape, not meaning. Three numbered cards can still be the wrong three
  things, and the regex has no way to know. I use these checks to catch the *silent-empty* failure
  mode, not to certify the digest's correctness. For correctness, a separate grader (a small
  evaluator that scores the digest against a labelled set) is the right tool — that's outside
  this folder.
- Classifiers are lexical. An unusual error lands in `прочее` and is reported as unclassified,
  which is the honest outcome. If a class appears repeatedly, I add it to `CLASSES` in
  `postmortem.py`; the rule of thumb is "if it appeared three times in a week, it gets a
  pattern".
- Fingerprints are `job_id + first 160 chars of error`. A failure that recurs with a slightly
  different message will look new every time. That is a feature when the difference is real, and
  a known false positive when the only thing that changed was a timestamp in the error string.
- The briefing is only as current as the files it reads. A stale `CHANGELOG.md` produces a stale
  brief. The fix is upstream: whoever writes the change log writes it on every change, not in a
  weekly cleanup.

## Directory structure

```
20-task-evals-and-autopsy/
├── task_evals.py             # did the work happen: freshness, size, shape, streaks, queues
├── postmortem.py             # error → class → advice, each new failure once
├── briefing.py               # one short brief compiled from local state
├── examples/
│   ├── task_evals.json       # checks for output_fresh / no_failures / queue_clear
│   └── briefing.json         # paths to work backlog, changes log, health files, job list
└── tests/test_autopsy.py     # classification, dedup of seen failures, freshness + cards
```

## License

Apache 2.0 — see the repository `LICENSE`.

## Disclaimer

The classifier covers the failure modes of one real deployment. Extend the class list before
trusting it on another deployment; an `Error 502 from gateway` may not yet map to `доставка`.