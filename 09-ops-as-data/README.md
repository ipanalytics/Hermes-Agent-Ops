# 09 — ops-as-data

**Scheduled jobs as living documentation: stop writing the watch-table by hand, generate it from the job list.**

> The docs always drift from reality — until the docs ARE generated from reality.

## What you get here

- `cron_exporter.py` — renders a markdown watch-table from a JSON job list: when each job runs (humanized cron), with or without an LLM agent, where it delivers, notes, and who watches it. Deterministic, free, CI-able.
- `jobs.example.json` — the input schema, with five realistic jobs (digest, guard, monitor-gated price watch, weekend media digest, one-shot reminder).
- `README.md` — you are here.

## The loop it closes

1. Job list is the single source of truth (the scheduler already stores it — export it).
2. Exporter renders the table → commit it next to the ops docs (`05-cron-of-crons`).
3. Freshness rules ride along in the generated footer (Mon–Fri on Saturday = correct; no-LLM job printing nothing = healthy).
4. Wire it into the operator sweep: any diff between the generated table and the previous commit is an unannounced schedule change.

## Pairing

- `07-fresh-prompt-linter` guards the *prompts* of agent jobs; this guards the *schedule docs*.
- The export feeds the who-watches-whom matrix in `05-cron-of-crons` automatically.

## Why this gets stars

"Which crons even run here, and when?" is the first question of any agent-ops handover.
A generator that answers it from data — with the freshness rules encoded — is instant value,
and the drift-proofing story is a good one.
