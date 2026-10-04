# 28 — digest-delivery-health

_Russian version: [README.ru.md](README.ru.md)_

![License](https://img.shields.io/github/license/ipanalytics/Hermes-Agent-Ops)
![Status](https://img.shields.io/badge/status-active-brightgreen)
![Python](https://img.shields.io/badge/python-3.10+-blue)

Every morning my agents push a handful of digests onto my desk — short summaries of the day before: what moved on the markets, what the train did to my schedule, which peptide entry is worth a second look, what is new on arXiv. None of them is dramatic on its own, and that is exactly the problem: when one of them silently stops arriving, I don't feel the gap. I just have one fewer thing to read that morning. Two weeks later I might notice. By then I have missed a run of releases, a price drop, or a paper that would have changed my morning.

This folder is the script that catches that silence early. It reads the audit log — the JSONL file where every cron run leaves a one-line trace (timestamp, job id, whether the agent replied with content, whether it errored, how long it took) — and compares what actually fired against what the schedule says should have fired. The difference between the two is the digest health I care about.

A cron job, for anyone new to the term, is a task the operating system launches on a schedule by itself, without anyone clicking "run". An agent, in the sense I use the word here, is one of those scheduled tasks driven by a language model — a small Python script that asks a model for a digest and posts the result somewhere I will read it. The gateway is the small service in front of all of them: it brokers agent traffic, runs the cron schedule, and writes the audit log on every run. I run a few dozen cron jobs. Some run daily, some only on weekdays, some only on Monday, some only on Saturday. The mix matters: a missed Monday-only job is invisible until the next Monday, and a missed daily job is invisible until someone happens to remember it exists. I needed a single page that told me, every morning, which channels of mine stopped working — without opening nine mail clients and counting.

## Why it exists

The trigger was one missed morning digest. It was supposed to land at 06:00, and one Tuesday it didn't, and on Wednesday I was busy, and on Thursday I assumed Tuesday was a glitch, and on Friday I opened the inbox to a stack of news I would have wanted on Monday. The job had died five days earlier — a path in the prompt had been renamed during a refactor, and the agent had failed silently with a "no such file" error it considered harmless. Nothing had logged an alert because the gateway's audit log only records that the job ran; it does not record that the run delivered anything useful.

By the time I sat down to fix it, the same kind of gap had already cost me a Monday-only peptide digest (I noticed when the entries in my notes stopped incrementing) and a quiet weekend release roll-up (I noticed only because a colleague asked why I was not discussing a show that was trending). Three independent silent failures in the same week, and the only common fact was that I found out about each of them by accident.

The fix could not be "read the logs by hand every day" — I would stop reading the logs every day, within a fortnight. The fix had to be a script that did the boring part for me, that lived in cron itself so the check did not depend on my memory, and that produced a report I could glance at in fifteen seconds. That is what `digest_health.py` is.

One more thing the incident taught me: coverage is never one number. One silent week for a daily digest is an incident. The same silent week for a weekly digest is normal. A script that averaged everything together would either scream weekly or stay calm daily. I report each channel separately, with its own green/yellow/red light, and let the trend across weeks catch the slow drifts that a single week's report cannot.

## How it works

1. The script opens `~/.hermes/cron/jobs.json` and pulls out the current job catalog. Each entry has an id, a human name, and a schedule. If the file is missing or malformed, the script falls back to its own built-in list of known digests and keeps going — a degraded report beats no report.
2. It opens the audit log at `~/.hermes/cron/usage_audit.jsonl` — one JSON object per line, appended by the gateway on every run. It parses each line, drops the ones it cannot read, and keeps only the records that fell inside the last seven full UTC days (today is still ongoing and is not counted).
3. For every known digest, the script computes what should have happened in that window: a daily digest expects seven runs, a Monday-only digest expects the number of Mondays in the window, a weekday digest expects five, a Saturday-only digest expects one. That expected count is the contract the schedule implies; the audit log has the contract being kept, or failing to match.
4. For each digest it then calculates coverage as `actual / expected`, counts runs that came back silent (the agent replied with empty content), counts runs that errored, and remembers the longest single execution time in the window. Coverage below 80% or any error pushes the row to red; coverage under 100% keeps it at yellow; full coverage with no errors turns it green.
5. The script reads the previous week's snapshot from `~/.hermes/data/digest_health_state.json`, and for each row whose coverage is worse than last week's it appends a small downward arrow. The arrow is the cheap part of the report and the part I trust the most — a single yellow that gets worse over three weeks is the kind of signal that one yellow alone would not surface.
6. The whole result is written to stdout, and the new snapshot is written to the state file atomically — written to `digest_health_state.json.tmp` first and then renamed into place with `os.replace`, so a crash mid-write cannot leave a half-finished state file that the next run reads as truth. The stdout line is what my cron gate (the upstream check that watches one script's output and raises an alarm when the output changes or goes silent) latches onto if I want to escalate on red.

The script itself runs from cron. A monitoring script that requires me to remember to run it is not monitoring.

## The digests I track

The script currently knows about nine digests by id and short name; the schedule is encoded directly in the script as a small lambda per digest. The list is what I have today; the file is short on purpose, and I edit it when I add a new one.

| Short name | Expected in 7 days |
|---|---|
| `morning-releases` | 7 (daily) |
| `weekday-day-releases` | 5 (Mon–Fri) |
| `weekend-releases` | 2 (Sat–Sun) |
| `morning-train` | 5 (Mon–Fri) |
| `ai-digest` | 7 (daily) |
| `peptides-mon` | number of Mondays |
| `gene-digest` | 7 (daily) |
| `streaming-mon` | number of Mondays |
| `expense-sat` | number of Saturdays |

The expected counts are computed in UTC, which is the timezone my gateway runs in and the one my cron schedules are written against. Running this against a different timezone means the numbers mean nothing until they are converted.

## Quick start

```bash
# Set required environment variables
export HERMES_AUDIT_LOG=~/.hermes/cron/usage_audit.jsonl
export HERMES_JOBS_FILE=~/.hermes/cron/jobs.json
export HERMES_DIGEST_HEALTH_STATE=~/.hermes/data/digest_health_state.json

# Run the script
python3 digest_health.py
```

The script takes no command-line arguments. Anything I want to tune — the list of digests, the coverage thresholds, the slow-run threshold of 120 seconds — lives as constants at the top of the file. I have not moved them into configuration yet because there has been no second deployment; that is the kind of refactor that earns its keep only after a second copy of the script is running somewhere.

## Outputs

A short markdown report, printed to stdout. The shape of a row is `<light> <name>: <actual>/<expected>`, followed by `silent N`, `errors N`, or `slow N s` when those numbers are non-zero, with a downward arrow when this week's coverage is worse than last week's. The lights are red for any row with errors or coverage below 80%, yellow for coverage below 100%, green otherwise.

Below the table, when at least one row is yellow or red, the script appends the reminder `There are gaps — see last_error/check, fix if repeated for 2+ days.` A single yellow is not yet an incident; the same yellow showing for the second day in a row is.

The state file at `~/.hermes/data/digest_health_state.json` holds last week's snapshot — week start, per-digest expected/actual/silent/errors/coverage. It is the only piece of state the script keeps, and the file is overwritten atomically on every run.

## Limitations

- The script trusts the audit log format. A malformed line is dropped silently and that day's run disappears from the report. The line-drop count in the gateway's own log is the separate signal I keep against this.
- All window math assumes UTC. Daylight-saving changes in my local timezone do not move the boundaries of the seven-day window, which is what I want.
- The list of known digests is hard-coded in the script. Adding a tenth digest means editing the file; forgetting to do it after adding a new cron job means the new job is invisible to this check until I notice. I keep that loop tight because the price of forgetting it is exactly the silence this script is meant to catch.
- Historical analysis only looks at two adjacent weeks. A long-running drift over a month will show as "this week is worse than last week" until the trend catches up; that is by design — long history is what `BENCHMARKS.md` is for.
- The state file holds the previous week's snapshot, not a full history. Deleting the state file is fine: the next report simply has no trend arrow.

## Structure

- `digest_health.py` — the script itself
- `tests/test_digest_health.py` — unit tests for the weekday-counting helper (`_weekdays`)
- `examples/jobs.json` — a tiny sample of the jobs catalog with two entries, enough to exercise the load path
- `examples/usage_audit_sample.jsonl` — one example audit record with the fields the script reads (`ts`, `job_id`, `response_silent`, `error`, `duration_ms`)
- `README.md` — this file
- `README.ru.md` — the same thing in Russian

## Related

- **27-research-scout** — one of my scheduled jobs whose delivery this script checks. A missed arXiv briefing is exactly the kind of quiet gap I want caught.
- **30-schedule-audit** — where I decide which jobs may move to night hours; this script verifies they kept doing it after the move. If a job moved to 03:00 stops reporting, I want to know before the next daytime run, not after.

## License

MIT License — see the LICENSE file in the repository for details.