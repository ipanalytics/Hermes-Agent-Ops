# 09 — ops-as-data

_Russian version: [README.ru.md](README.ru.md)_

My scheduled jobs, exported as the documentation that describes them. I used to write the watch-table — the list of which job runs when and who is responsible for watching it — by hand. Then I made it generate itself from the scheduler's job list, and the table stopped drifting the moment any job moved.

> The docs always drift from reality — until the docs ARE generated from reality.

## Hermes, in one paragraph

Hermes is the AI agent that lives on my server. He runs work on a schedule (those are *cron jobs*, fired by a small scheduler that triggers each one at its fixed time, unattended) and on demand. He produces digests, watches prices, guards balances, audits his own crons, lints his own prompts, and writes scripts for himself. This folder is one of those pieces: the part that keeps the documentation of his schedule honest.

## Why it exists

Two artefacts used to live side by side: the scheduler's job list (truth) and a markdown table I wrote by hand (docs). Within weeks they always disagreed. A job moved from `06:00` to `05:30`, a delivery target changed from `local` to `topic: alerts`, a one-shot reminder self-disabled, and the table kept describing the past. Nobody noticed until a real digest went missing because two people thought the other one was watching it.

The fix is mechanical: stop writing the table, render it from the same list the scheduler already stores. There is nothing left to keep in sync by hand. Any diff between the generated table and the last commit becomes a signal — an unannounced schedule change — instead of a chore.

## What's here

- `cron_exporter.py` — reads a JSON job list and renders a markdown watch-table. The table shows, for each job, when it runs (cron converted to a human-readable string), whether it uses an LLM (large language model) agent or is just a plain script, where it delivers its output, free-form notes, and who watches it. The script is deterministic — same input, same output — free to run, and small enough to live in CI.
- `jobs.example.json` — the input schema with five realistic jobs: a daily train digest (Mon–Fri), a balance guard (every 30 minutes, no agent), a monitor-gated price watch (LLM only wakes when the RSS diff is non-empty), a weekend media digest (sends only the delta versus its previous run), and a one-shot kitchen reminder (absolute timestamp, self-disables after firing).

## The input schema

Each job is one JSON object:

```json
{
  "id": "ab12cd34",
  "name": "morning train digest",
  "schedule": "0 6 * * 1-5",
  "agent": true,
  "deliver": "topic: commutes",
  "notes": "Mon-Fri only; deviations only, silence when on schedule",
  "watcher": "operator"
}
```

- `schedule` is a five-field cron expression (minute, hour, day-of-month, month, day-of-week) — or, for one-shots, an absolute ISO timestamp.
- `agent: false` means a no-LLM script job — the model never wakes. The output is what the script says; no thinking tokens are billed.
- `deliver` is where the job's result lands: a topic on the chat side, the local filesystem, an alert channel, or a direct message to me.
- `watcher` is who is on the hook if the job goes silent. The default is me (operator).

## The loop it closes

1. **Job list — single source of truth.** The scheduler already stores it; I export it as JSON.
2. **Exporter renders the table.** I commit the output next to the ops documentation in `05-cron-of-crons`. The table is a *do not edit by hand* file: any human edit there gets overwritten next run.
3. **Freshness rules ride along in the footer.** Mon–Fri jobs on Saturday are CORRECT, not an incident. A job delivering `local` never messages me — its output feeds another job downstream. An no-LLM job that prints nothing is healthy: empty stdout is silence is zero cost.
4. **Wire the export into the operator sweep.** Any diff between the generated table and the previous commit is an unannounced schedule change. The diff itself is the alarm.

## Humanising cron

The exporter turns `0 6 * * 1-5` into `06:00 UTC Mon–Fri` and `*/30 * * * *` into `every 30 min`. The cases I see most often:

| cron expression | humanised |
|---|---|
| `*/30 * * * *` | every 30 min |
| `0 6 * * 1-5` | 06:00 UTC Mon–Fri |
| `15 11 * * *` | 11:15 UTC every day |
| `0 10 * * 7` | 10:00 UTC Sun |
| `2026-09-09T15:30:00` | `2026-09-09T15:30:00` (one-shot, kept verbatim) |

The humanised form is what gets read out during the operator sweep — I don't want to parse cron in my head at 7 a.m.

## Pairing

- `07-fresh-prompt-linter` guards the *prompts* of agent jobs (a bad prompt wastes tokens and burns trust). This folder guards the *schedule* documentation.
- The export feeds the who-watches-whom matrix in `05-cron-of-crons` automatically. One script, two consumers.

## Limits

- The exporter only knows what the scheduler stores. If the scheduler and the real workload drift — a script that does something the JSON never mentioned — this folder will not catch it. The operator sweep does.
- `humanize()` is best-effort: anything it does not recognise falls back to the raw cron expression. I keep my expressions boring on purpose, so the humaniser rarely has to guess.