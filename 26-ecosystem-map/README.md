# 26 — Ecosystem Map

_Русская версия: [README.ru.md](README.ru.md)_

![License](https://img.shields.io/github/license/ipanalytics/Hermes-Agent-Ops)
![Status](https://img.shields.io/badge/status-production-brightgreen)
![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue)

Hermes is my home AI agent. It lives on a server of mine, runs around the clock, and does most of its own routine — daily digests, price watches, health checks, even looking at its own logs for failures. Almost all of that runs as a "scheduled job" (cron — a task that fires at fixed times with no human in the loop). The jobs live in a single JSON file; each one is pinned to a model (the LLM that does the work) or a deterministic script, an address where its output lands (a Telegram chat, a topic inside a group chat, or a local file), and a state — `scheduled` (active), `paused` (held), or `completed` (a one-off that has already fired).

At some point that list grew past what fits in my head. My deployment now carries dozens of jobs spread across fourteen Telegram topics, several local collectors feeding downstream scripts, and a manual I could no longer keep true. This folder is the small script that draws the live picture: every Monday at 05:30 UTC it rebuilds the full map from the job list and prints only the diff against the previous run, so I see what appeared, what paused, what flipped to failing — without re-reading `jobs.json` by hand.

## Why I built it

I noticed the documentation had drifted twice, in the same shape, before I built this.

The first time, a job I thought was delivering to the `System` topic started writing to the `News` topic instead. The `deliver` field in `jobs.json` had moved; the comment in `watch-table.md` did not. Nobody told me for a week, because nothing about the job had failed — it was happily producing output, just into the wrong topic.

The second time was worse. A job that fed a downstream weekly report had been silently dead for two months. It was still marked `scheduled` in the list, still had a future-looking cron expression, still had a fresh-looking `last_run_at` because a different run had touched that field. The actual job body had stopped executing six weeks earlier. I only found out because the report it fed had been empty for two months, and a job downstream of *that* finally noticed and complained.

Both incidents had one cause: the configuration moved on, and the documentation did not keep up.

Static tables — `watch-table.md` from module 05, or the README of this very repository — work as long as someone maintains them. Nobody was maintaining them; I had been treating them as furniture. The exporter in `09-ops-as-data` does generate documentation from the job list, but it is a one-shot: it runs when I run it, and I was not running it. I needed something that ran on its own, every Monday, on no LLM, and told me what changed.

That is the script in this folder.

## What the script does, briefly

It is a no-agent job (no model in the loop — pulling a model in just to render a list would burn tokens for nothing, and the model would not have anything to add). It reads the job list, reads the profiles directory, writes a fresh Markdown map, and prints the diff to stdout. The scheduler picks up that stdout; if there are no changes, stdout is empty and the scheduler stays silent. Silence is the healthy state. That is the watchdog pattern from `05-cron-of-crons`: an empty stdout is the report "still healthy", not the absence of a report.

## What the map contains

The full map (written to `~/.hermes/data/ecosystem_map.md`) has five blocks:

- **Header line** — generation timestamp in UTC, plus the `updated_at` field of the `jobs.json` file the map was built from. Two timestamps because I want to know at a glance whether the map itself is stale, not just whether the script ran.
- **Crons total** — total jobs, broken into active / paused / completed one-offs. A growing paused count is a smell; a growing completed count is normal — those are reminders that fired once and self-disabled.
- **Profiles** — every profile in `~/.hermes/profiles/`, with `default` marked as main. A profile is an independent configuration of the agent: its own model selection, its own skills, its own topic walls. The map shows them so a job name that exists in two profiles with different delivery targets does not look like a bug in the map.
- **Problems** — any active or paused job whose last run ended in `error` or whose `failure_streak` is above zero, with the count of consecutive failures and the date of the last attempt. This is the first block I read on Monday.
- **Crons by delivery targets** — every scheduled and paused job grouped by where it delivers: direct messages to me (`📩 direct`), named topics (`t.16 'Media'`, `t.18 'Health'`, …), the second group chat if any, any other chat by its raw id, `local` for jobs that only write files, and `unrouted` for jobs whose `deliver` field is empty.

Each job row carries its short id (first 8 hex chars), the cron expression or schedule label, the kind of worker (`⚙️ scriptname.py` for deterministic scripts, `🤖 modelname` for LLM-backed jobs), and the last-run marker: `🟢 2026-10-04` for clean, `🔴 error ×3 (2026-10-04)` for failing, `⚪ not run` for jobs that have never fired.

## What the diff contains

The stdout printout is the artifact I actually read on Monday, and it only contains lines when something changed since the previous run:

- `➕ new cron: <name> (<schedule>)` — a job appeared in the list with state `scheduled` or `paused`.
- `➖ removed cron: <name>` — a job that was `scheduled` or `paused` last week is gone.
- `resumed ▶️: <name>` or `paused ⏸: <name>` — a job changed state between `scheduled` and `paused`.
- `⚠️ <name>: 🔴 error ×N (date)` — a job that was healthy last week is now failing.

That is the whole list. If nothing changed, the script prints nothing; the scheduler sees empty stdout and delivers nothing. I do not get a "still healthy" message on a quiet week — the absence of a message is the healthy signal, exactly like the wallet guard in module 01 and the gateway supervisor in module 02.

## How it works

The script reads from three places and writes to two:

- Reads `~/.hermes/cron/jobs.json` — the canonical job list. Each entry carries `id`, `name`, `state`, `last_run_at`, `last_status`, `failure_streak`, `schedule_display`, `model` (or `script` for no-agent jobs), `deliver` (the delivery target), and `origin` (chat id and thread id for the source).
- Reads `~/.hermes/profiles/` — every subdirectory is a profile; the script lists them with `default` first and tagged as main.
- Reads `~/.hermes/channel_directory.json` — friendly names for Telegram chats and topics. The constants `TOPIC_NAMES` at the top of the script map topic numbers to names: `16 → Media`, `17 → Travel`, `18 → Health`, `19 → Other`, `20 → Wearables`, `30 → System`, `35 → Kitchen`, `82 → HQ`, `105 → Models`, `239 → Genetics`, `713 → Authorities`, `762 → Security`, `763 → News`, `1078 → Mail`. The environment variables `HERMES_GROUP_CHAT` and `HERMES_SECOND_CHAT` tell the script which numeric chat IDs are the group chats it should resolve topic numbers for; `HERMES_OPERATOR_CHAT` is the chat id where a direct message to me should be rendered as `📩 direct` rather than the generic `chat <id>`.

Writes to two files in `~/.hermes/data/`:

- `ecosystem_map.md` — the full Markdown map, atomically replaced: write to `.tmp`, then `os.replace`.
- `ecosystem_map_state.json` — the snapshot the next run diffs against. Carries the generation timestamp and a per-job record of name, state, and an `_err` flag derived from `last_status == "error"` or `failure_streak > 0`.

Atomic writes are the part that matters: the map is rebuilt while something else might be reading it. A partial map would corrupt the next diff by attributing removals that never happened.

## Quick start

```bash
# Run once — builds the map and the first state snapshot, prints nothing (no previous state to diff against).
python3 ecosystem_map.py

# Run again later — prints the diff of what changed since the first run, and rewrites the map.
python3 ecosystem_map.py
```

In deployment the script sits in a no-agent cron job, Monday 05:30 UTC. The scheduler is responsible for picking up stdout and delivering it; the script itself only writes the two files in `~/.hermes/data/`.

## Configuration

There are no flags and no config file. Three environment variables are read for chat resolution:

- `HERMES_GROUP_CHAT` — chat id of the main group chat where topics live.
- `HERMES_SECOND_CHAT` — chat id of a second group chat, if any.
- `HERMES_OPERATOR_CHAT` — chat id where direct-to-me deliveries land.

If these are not set, `📩 direct`, the group-topic references, and `second group` simply fall back to `chat <id>`. The map still gets built; the labels just become less readable.

## Outputs

- `~/.hermes/data/ecosystem_map.md` — full Markdown map of every scheduled and paused job, grouped by delivery target.
- `~/.hermes/data/ecosystem_map_state.json` — snapshot the next run uses for the diff.
- stdout — the change diff, only when there are changes. The scheduler picks this up.

## Limitations

- The diff only watches jobs in state `scheduled` or `paused`. A `completed` one-off that disappears is silent by design — the system already considers it done.
- Grouping depends on `deliver` being filled in for each job. A job with no delivery target lands in `unrouted` until I set one. The map surfaces the count; the fix is on me.
- Delivery to Telegram is the scheduler's job, not this script's. If the scheduler is misconfigured, the diff will be generated correctly and simply never reach me.
- The script does not detect removals inside the `completed` state, only additions and removals among the active jobs. The completed list grows monotonically until I clean it up by hand.

## Structure

```
ecosystem_map.py              # Main script
README.md                     # English documentation
README.ru.md                  # Russian documentation
tests/test_ecosystem_map.py   # Unit tests
examples/jobs.json            # Sample job list for tests
```

## Related

- **05-cron-of-crons** — the who-watches-whom matrix that decides this job's place in the schedule, and the source of the "silence is healthy" rule.
- **09-ops-as-data** — the one-shot exporter that also renders the job list, but does not run on its own; this folder is the live version of the picture 09 describes.
- **30-schedule-audit** — the deeper sweep that reviews when jobs fire and which of them cost real money; this folder is the live map, that one is the audit.

## License

MIT