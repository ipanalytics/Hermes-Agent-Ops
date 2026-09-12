# 05 — cron-of-crons

_Русская версия: [README.ru.md](README.ru.md)_

**Self-observing scheduled jobs: the operator sweep, freshness checks, and the who-watches-whom chain.**

## What you get

- `operator_prompt.example.md` — the daily sweep brief: self-contained, economy-minded, output format (one line when normal, ⚠️/🔴 per incident), dedupe via continuity, **schedule-aware freshness**, deliberate exclusions.
- `watch-table.md` — the who-watches-whom matrix + survival analysis (what survives a gateway restart) + the rule: every watcher is watched by a different layer that survives it.
- `delivery-policy.md` — local vs topic vs alert decision table; monitor-gated LLM runs; empty-stdout watchdog pattern.

## The problem

Scheduled LLM jobs drift: a delivery error, a silently skipped day, a job pinned to a dead model, a freshness check that doesn't know weekends exist. If nothing watches the watchers, you discover it a week late.

## The patterns (summary)

### The operator sweep (daily)
Checks: jobs enabled? delivery/fire errors? health (disk/RAM/zombies)? **freshness per each job's real schedule**? artifact hygiene? Reports: normal → one line; incidents → line-by-line; no change → "no change". Runs on a *different* model than the jobs it reviews. Some domains are deliberately excluded from oversight — documented, not an oversight.

### The who-watches-whom chain
cron → script → external daemon → guard cron. Every layer is watched by a *different* layer that survives the thing it watches. No self-referential healing.

### Delivery discipline
Data collectors deliver locally (never message the user); real alerts go to a topic; one-shot reminders are fixed-text no-agent jobs that self-disable.
