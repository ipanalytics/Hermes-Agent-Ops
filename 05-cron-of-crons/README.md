# 05 — cron-of-crons

_Russian version: [README.ru.md](README.ru.md)_

![License](https://img.shields.io/github/license/ipanalytics/Hermes-Agent-Ops)
![Status](https://img.shields.io/badge/status-active-brightgreen)

**My kit for the work an agent does on a schedule.** "Cron" is just the name of the scheduler that fires a task unattended at a fixed time; "of-crons" is the layer that watches that scheduler. This folder keeps three things in order: the daily operator sweep that reviews every scheduled job, the freshness checks that match each job's real schedule (a Monday-to-Friday job is *not* stale on Saturday), and the who-watches-whom chain — the rule that every watcher is itself watched by a different layer that survives it. The reason I keep it is simple: I hear about a dead or drifting job within a day, not a week later, and I never have to trust a job to report on itself.

## Why I built it

Scheduled LLM jobs drift. A delivery error that never resolves. A day the job did not fire and did not tell me. A job pinned to a model that is no longer served. A freshness check that does not know weekends exist and starts reporting stale at midnight Sunday. None of those failures announce themselves in the log — they just quietly stop producing output.

I paid for this lesson once. A job that watched a few other jobs died, nothing watched *it*, and I learned about the failure a week later — after a week of empty digests in my morning topic. The fix was not "add more alerts". The fix was a chain in which every layer is itself supervised by a different layer that survives it. Three rules fall out of that fix and run through this folder:

- **The reviewer cannot be the same model as the worker.** A controller that runs on the same model as the jobs it reviews can die together with what it reviews. The operator sweep runs on a third model.
- **A freshness check must know each job's real schedule.** "Last ran" is not enough: a Mon–Fri job is correct on Saturday; a weekly job on Tuesday after a Monday holiday is suspect. The schedule is stored next to the job name and consulted before any alert fires.
- **An alert fires on the state transition, not on every poll.** A two-hour outage must produce roughly two messages, not two hundred. Each watchdog carries a state file: first sighting posts, repeats are suppressed until the state clears or a thirty-minute reminder fires.

## What is in the folder

- `operator_prompt.example.md` — my daily sweep brief. Drop-in for a scheduled job. A cron job runs in a fresh session with no chat history, so this prompt must carry everything: the checks, the exclusions, the fixed output format (one line when normal, ⚠️/🔴 per incident, `sweep N: no change` when nothing changed). It is economy-minded on purpose — unnecessary model calls cost money, and the operator does not need them.
- `watch-table.md` — the who-watches-whom matrix. Six rows: an external supervisor daemon that watches the gateway, a guard cron that watches the supervisor, the operator sweep that watches every scheduled job (on a third model), a balance guard that watches API spend, a weekly memory consolidation that watches memory bloat, and a daily backup job that watches the restore point. The matrix also includes the survival analysis (who lives through a gateway restart) and the rule that everything in this chain must be watched by a different layer that survives it.
- `delivery-policy.md` — the decision table for where a scheduled job's output goes: local file (data collectors that feed a downstream job), topic (real alerts, content digests), or a one-shot fixed-text message (life reminders, no agent, auto-disable after firing). The file also documents the alert-noise budget: transition-only alerts, silent recovery for short self-restarts, a reminder at most every 30 minutes, and a cap on how often a wallet guard may fire in a healthy day.

## How it works

### The operator sweep (daily)

The sweep runs once a day and checks, in this order:

1. **Jobs enabled?** Delivery or fire errors? Jobs paused that should be running, or running that should be paused?
2. **System health.** Critical error count, ignoring the known non-alarms (`browser`, `discord`, `feishu`, `x_search`). Disk under 80%? RAM under 90%?
3. **Forgotten sessions.** Zombie terminal sessions that nobody is using.
4. **Freshness, per real schedule.** Train status is Mon–Fri daily — Saturday is correct, do not report it. Weekly research fires on Mondays. Dataset job fires daily at 11:00. Battery survey fires every two days. A weekly job that did not fire on a Monday holiday is something to look at; the same job firing on Tuesday because Monday was a holiday is normal.
5. **Artifact hygiene.** Release counts and sizes; leftover artifacts trigger the cleanup script, which keeps the newest per repo.

Reporting is fixed format too. Normal → `OPERATOR sweep <time>: jobs OK, system OK, artifacts OK, no anomalies`. Incidents → one line each, severity in front. No change → `sweep N: no change`. Continuity (the sweep sees its own previous output) is the cheap dedupe: if the next line would be the same as the last one, it is suppressed.

Some domains are deliberately excluded from oversight — the chef's kitchen, the user's private topics, memory entries that hold personality or infrastructure state. Exclusions are a feature, not an oversight: they are written next to the watch table so a future operator does not "fix" them back into scope.

### The who-watches-whom chain

The shape is always the same: cron → script → external daemon → guard cron. Every layer is watched by a *different* layer that survives it. Survival through a restart decides the design: a process spawned from the agent's terminal does not survive (its PID is a child of the gateway); a process spawned by the scheduler does; a detached external daemon does (and the guard cron re-spawns it as belt-and-braces). I have watched an update wrapper restart the gateway twice and never finish its own cleanup — the post-restart work belongs to a layer that lives past the restart.

### Delivery discipline

A data collector that only prepares files for a downstream job delivers **locally** — the user does not want raw `OK: sleep=78 ready=69` lines. A real alert or threshold breach goes to the **user's alert topic** (first line, big, with a plan B). A content digest (movies, research, peptides) goes to **its own topic** in verbose cards. A service delta with no change is **silence or a single line**. A one-shot life reminder is a **fixed-text no-agent job** that self-disables after firing.

Two implementation details matter. **LLM-gated runs**: put a cheap change-detector in front of the LLM job; identical output to the previous tick skips the agent entirely — that is how digest costs stay flat week-over-week. **Continuity**: the cheap dedupe for digests is "the job sees its own previous output" — compare, send only the delta.

### The alert noise budget

A two-hour outage must produce roughly two messages, not two hundred. The rules: **transition-only alerts** gated on a state file (I have watched one sick service generate thirty-plus messages in ninety minutes); **silent recovery is the norm** — a unit that restarts itself and comes back in under a minute needs no alert, that is `Restart=on-failure` doing its job; **reminder, not replay** — one short reminder at the thirty-minute mark is useful, re-sending the same alert every cycle is not; **budgets scale with severity** — a wallet guard fires a few times a day by design, a supervisor caps at three retries per hour then escalates; **the human's topic is a fire channel**, not a content feed — if it accumulates more than a handful of messages on a healthy day, the policy is wrong.

## What the prompt looks like in practice

The `operator_prompt.example.md` file is the brief I drop into a scheduled job. It is self-contained on purpose: a cron job runs in a fresh session with no chat context, so the brief must carry everything — the daily order, the output format, the exclusions, the rule "I am the reviewer, not the fixer" (report precisely, fix only what the coordinator pre-approved). Copy-paste ready; the parts that depend on the deployment (the actual job list, the names of excluded domains) live as environment or as a small file next to it.

## Related

- **02-agent-gateway-supervisor** — the supervisor daemon this folder's chain depends on; without it, the chain collapses on the first gateway restart.
- **03-agent-ops-playbook** — the incident that turned "scheduled jobs drift silently" from an observation into a rule.
- **09-ops-as-data** — generates its watch-table from the live job list, so the table in `watch-table.md` is a working template, not a manual.
- **14-agent-data-intake** — applies the same alert-noise-budget rule to the device-receiver watchdog: one alert per incident, one reminder per thirty minutes, nothing on a self-recovered restart.

## License

MIT License — see the LICENSE file in the repository root.