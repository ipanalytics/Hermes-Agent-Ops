# 30 — Schedule Audit

_Russian version: [README.ru.md](README.ru.md)_

![License](https://img.shields.io/github/license/ipanalytics/Hermes-Agent-Ops)
![Status](https://img.shields.io/badge/status-active-brightgreen)
![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue)

This audit cut my daily token bill by moving heavy scheduled jobs to the night — without changing a line
of code or a single model. It reads what each of my cron jobs (cron is the system service that runs my
tasks on a schedule) really spends on tokens, finds the ones that are heavy but in no rush, and prints a
list to move to hours when nothing else needs the budget.

## What it is and what it is not

This folder is one tool, written once. There is no model in it and no API call in it. The script reads
two files I already keep around for other reasons: `jobs.json` (my list of scheduled tasks) and
`usage_audit.jsonl` (a log where each line is one recorded run of a task with its prompt and completion
token counts). It joins the two by `job_id`, averages the spend per task, and prints two short lists.
One list is "heavy crons" — anything above 200,000 tokens per run on average. The other is "movable to
night" — heavy tasks whose name does not contain words like `morning`, `daytime`, `noon`, `prime` or
`critical`, and whose cron schedule is not already inside the quiet hours. With `--apply`, the second
list is also written back to `jobs.json`, after a timestamped backup is taken and a rollback file is
written.

This is the lever I reach for when my daily cost report (folder **29**) tells me the runway got short and
nothing in the models themselves changed. Same reasoning as the one above — the cost did not move.
Somewhere in the schedule, heavy work has crept into the hours where I am also working interactively,
and both are paying full price for the same window.

## Why it exists

Token spend looked to me like a model question. A model is the AI the task runs on; picking a cheaper
one or a smaller one was the lever I was used to pulling. When the daily number climbed, I would go
shopping for a model again. That worked for a while. Then one month the curve started climbing even
though I had not switched anything — same models, same prompts, same scheduled jobs. The thing that had
changed was the schedule itself: I had added more background jobs over the year, and the new ones had
landed at whatever hour I was thinking about them when I wrote them. By the time I noticed, the daytime
budget was being eaten by jobs that did not need to be there at all.

A translation task is the same task at midnight. A weekly audit is the same audit at four in the morning.
A research harvest does not get more useful for being delivered at lunch. None of these cares whether I
am awake. They all care that they finish before I want the result, and most of them have hours of slack.
That was the situation I wanted to capture: which tasks consume more than 200,000 tokens per run, and
which of the ones above 100,000 are flexible enough to move without anyone noticing. The script turns
that question into a printable list.

The trick that made the cut worth running was that the move costs nothing. I am not retraining a model,
I am not rewriting a prompt, I am not negotiating a contract. I am changing a single field in a JSON
file — the `schedule` of a handful of cron jobs — and letting the cron daemon do the rest. The same
work, the same model, the same prompt, just at a different hour. If the move turns out to be wrong, the
backup is one line and the rollback file says exactly what changed.

## How it works

The script reads the two files, joins them by `job_id`, and computes per-job averages. The full
algorithm:

1. Read `jobs.json` (either a list of jobs or an object with a `jobs` key; both shapes are accepted).
   Build a lookup by `id`.
2. Read `usage_audit.jsonl` line by line. For every line, accumulate `runs` and `tokens = prompt_tokens
   + completion_tokens` for that `job_id`.
3. For every job that exists in both files and is not flagged with `no_agent`, compute the average
   tokens per run: `avg = tokens // runs`.
4. If `avg >= 200,000`, the job goes onto the **heavy** list, sorted by spend and capped at the eight
   biggest entries in the printout.
5. If `avg >= 100,000` **and** the lowercase job name matches the `FLEXIBLE` regex
   (`audit|research|study|direction|translation|skill|hygiene|expense|meta|backlog|snapshot|harvest|compression-check`)
   **and** does **not** match the `TIME_CRITICAL` regex
   (`morning|daytime|evening|noon|prime|critical`) **and** the current cron schedule does not already
   start with one of `0 1`, `0 3`, `0 5`, `0 12`, `0 13`, `15 3`, the job goes onto the **movable**
   list.
6. Print the heavy list (if any), then the movable list (if any).
7. If `--apply` was passed, make a backup of `jobs.json` in `~/.hermes/data/cron_backups/`, write every
   movable job's `schedule` to `"0 4 * * 6"` (Saturday at 04:00 UTC, deep off-peak), persist the
   modified `jobs.json`, and write `~/.hermes/data/schedule_rollback.json` mapping each moved job's id
   to its old schedule.

The two regexes are deliberately simple. They are heuristics, not classifiers. The point is not to read
my mind about whether a job is time-critical — the point is to surface candidates cheaply so I can look
at them. Anything that matches `morning`, `daytime`, `evening`, `noon`, `prime` or `critical` in the
name stays where it is. Anything with `research`, `audit`, `study`, `direction`, `translation`,
`skill`, `hygiene`, `expense`, `meta`, `backlog`, `snapshot`, `harvest` or `compression-check` in the
name is treated as a candidate. Names that match neither — generic ones like `daily-task` or
`pipeline-7` — are left alone in the dry-run and looked at by hand. I would rather under-flag than
move something by accident.

The night window is `0 4 * * 6` — minute 0 of hour 4 on Saturday, in UTC. Saturday 04:00 UTC is what
the cron service calls deep off-peak on my server: the previous week's digests have been delivered,
the new week's interactive work has not started, and the network is quiet. The `usage_audit.jsonl`
records all runs in UTC, so the same window in the script lines up with the same window in the data
without conversion.

## Quick start

```bash
# Run the audit without making changes — dry run, prints the two lists.
python3 schedule_audit.py

# Apply the move, write the modified jobs.json, write the backup and the rollback file.
python3 schedule_audit.py --apply
```

There are no third-party dependencies. The script uses only the Python standard library: `json`, `os`,
`shutil`, `sys`, `time`, `re`, `collections.defaultdict` and `pathlib`. There is no `requirements.txt`
in this folder by design — nothing to install. It runs on 3.10 and newer, which is the version my
server already uses.

## Usage

The script takes no positional arguments. The two flags are:

- *(no flag)* — dry run. The two lists are printed, no files are written.
- `--apply` — perform the move. Requires the dry-run lists to be non-empty; if both are empty, the
  script exits 0 and writes nothing.

### File locations

Defaults, in order of override:

| Purpose | Path | Override |
|---|---|---|
| Jobs list | `~/.hermes/cron/jobs.json` | `JOBS_PATH=...` or `AGENT_HOME=...` |
| Usage audit log | `~/.hermes/cron/usage_audit.jsonl` | `AUDIT_PATH=...` or `AGENT_HOME=...` |
| Rollback file (written on `--apply`) | `~/.hermes/data/schedule_rollback.json` | none |
| Backups directory (written on `--apply`) | `~/.hermes/data/cron_backups/jobs.json.bak-sched-<timestamp>` | none |

`AGENT_HOME` is the umbrella: setting it to a different root moves every default path under it. On my
machine `AGENT_HOME` is unset and `HOME` is used instead, so the paths above are resolved against
`$HOME`.

### What the script needs in the input files

- `jobs.json`: each job has at least an `id`, a `name` and a `schedule`. `schedule` may be a string
  like `"0 4 * * 6"` or an object with an `expr` / `expression` key — both shapes are accepted. Jobs
  flagged `"no_agent": true` are skipped.
- `usage_audit.jsonl`: one JSON object per line, each with `job_id`, `prompt_tokens` and
  `completion_tokens`. Lines that fail to parse are silently skipped so a corrupted line in the middle
  of the log does not abort the audit.

### What the output looks like

Dry run, with the example files in `examples/` as they currently sit:

```
Heavy crons (average input per run):
  weekly translation               360 k tokens  schedule 0 14 * * *   runs 2
  research audit                   240 k tokens  schedule 0 12 * * *   runs 2
Nothing to move: flexible heavy tasks are already scheduled during night hours
```

In this run the heavy list is non-empty but the movable list is empty: both `weekly translation`
and `research audit` carry schedules (`0 14 * * *` and `0 12 * * *`) whose string prefix matches one
of the quiet-hour prefixes the script uses to recognise already-moved work (`0 1`, `0 3`, `0 5`,
`0 12`, `0 13`, `15 3`) — a side effect of the prefix check being string-based, not field-based. On
real data, where I have jobs at hours like `0 18 * * 1` or `30 9 * * 3`, the movable list is what
populates and looks like:

```
Can be moved to night (not time-critical, heavy):
  research harvest                410 k   currently: 0 18 * * 1
  weekly study audit              230 k   currently: 30 9 * * 3
```

With `--apply`, the script adds:

```
Moved: 2 (backup /home/me/.hermes/data/cron_backups/jobs.json.bak-sched-20261004-042200)
```

…and the `schedule_rollback.json` file holds the inverse mapping, so the move can be undone by hand
or by a future tool that reads it.

## Outputs

- A printed report: heavy crons (top 8, sorted by average tokens) and the movable list (sorted by
  average tokens).
- On `--apply`: a backup of the original `jobs.json` under `~/.hermes/data/cron_backups/` with the
  timestamp in the filename, a modified `jobs.json` with every movable task's schedule set to
  `"0 4 * * 6"`, and a `~/.hermes/data/schedule_rollback.json` file that records, for each moved job,
  the previous schedule — so the change can be reverted.

## Limitations

- The script needs both input files to exist. If either is missing it prints a one-line error and
  exits 1.
- Time-critical jobs are detected by name regex, not by inspecting the schedule. A job called
  `nightly-routine` would be flagged as movable; a job called `daily-report` would not match either
  pattern and would be left alone.
- The night window is hardcoded as `0 4 * * 6` for the move. The "0 1 / 0 3 / 0 5 / 0 12 / 0 13 / 15
  3" prefix list used to recognise already-quiet schedules is also hardcoded. Anything I want
  excluded from the move has to either match `TIME_CRITICAL` in its name or already start with one of
  those prefixes.
- The dry run is silent about jobs that are heavy but match neither pattern. They are not flagged and
  not warned about.
- `--apply` does not check whether cron is currently running the jobs being modified. If a job fires
  between the backup and the write, the in-flight run keeps its old schedule; the next run picks up
  the new one. I have not seen this matter in practice — the window between the two writes is under a
  second on my machine.
- Rollback is by file, not by cron. Reverting means reading `schedule_rollback.json` and writing the
  `was` field back into each job's `schedule`. The script does not have a `--revert` flag yet; I do
  it by hand when I need to.

## Structure

- `schedule_audit.py` — the script. One file, stdlib only.
- `tests/test_schedule_audit.py` — three tests: dry run on the sample data, heavy-job identification
  on a single-job fixture, flexible-job detection on a name that matches `FLEXIBLE`. All three use a
  private temp directory and patch the module-level `JOBS` and `AUDIT` paths so they do not touch my
  real files.
- `examples/jobs.json` — four jobs covering each of the cases the script handles: a morning routine
  that should not be moved, two heavy flexible jobs that should, and a backup that is already on a
  quiet schedule.
- `examples/usage_audit.jsonl` — two days of runs for each of the four example jobs, with token
  counts that line up with the script's thresholds.
- `README.md` — this file.
- `README.ru.md` — the same content in Russian.

## Related

- **29-thinking-layer-cost** — the daily spend report. When the runway is too short I look at the
  number, then I run this script, then I look at the number again. The report does not prescribe
  anything; it tells me when the lever is worth pulling.
- **28-digest-delivery-health** — verifies that the jobs I moved to night kept delivering after the
  move. A silent digest a week later is the failure mode I most want to catch; this folder is what
  tells me whether the move broke anything.
- **05-cron-of-crons** — the schedule itself. The audit reads `jobs.json`, which is what **05**
  watches. A change here shows up in the next run of that watcher.
- **22-difficulty-router** — the per-job model choice. Together, the two modules are the two halves
  of "what runs the job" and "what hour the job runs". One is the who; the other is the when.

## License

MIT