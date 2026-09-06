# Hermes Agent Ops

**Operating LLM agents in production, 24/7 — battle-tested patterns, guards and tooling for [Hermes Agent](https://hermes-agent.nousresearch.com).**

This repository is a single home for everything we learned running a multi-agent Hermes ecosystem around the clock: cron jobs that watch other cron jobs, an external supervisor that resurrects the gateway, a wallet guard that catches runaway token burn, role profiles that keep a chef out of medicine and a doctor from spamming — and the playbook of incidents behind it all.

> Status: **v0.2 — real code and templates.** Every folder below contains runnable, sanitized artifacts (Python scripts, shell guards, prompt briefs, SOUL/config templates, incident write-ups) that ran in production for weeks — not stubs. English throughout.

---

## Why one repository?

All six ideas below are one story: *"how to keep LLM agents alive, sane, and affordable when nobody is watching."* They cross-reference each other (the playbook explains the incidents the tools prevent), so they ship together:

- One README tells the whole narrative — much stronger than six orphan repos with one star each.
- Tooling, patterns and docs live side by side; each folder stays independently readable and publishable.
- Later, if a component (e.g. `agent-wallet-guard`) gains independent traction, it can be split into its own repo with its history intact.

## Layout

| Folder | What it contains |
|---|---|
| `01-agent-wallet-guard/` | Runnable watchdog (Python) + config example: measures the *actual* API balance, finds the runaway session, silent when OK |
| `02-agent-gateway-supervisor/` | Runnable external supervisor (Python) + guard cron script: heartbeat, auto-restart with cooldown, forgotten-pause healing |
| `03-agent-ops-playbook/` | The playbook: chapter outline + sanitized incident autopsies + decision trees |
| `04-role-profiles/` | Usable template: SOUL.md master-prompt skeleton, per-role config example, routing docs |
| `05-cron-of-crons/` | Copy-paste operator sweep brief, who-watches-whom table, delivery policy |
| `06-hermes-plugins-skills/` | Packaged skill (one-shot reminder) + cron recipes (monitor-gated digest, watchdog chain) |

## Ground rules of this codebase

- **Silence = OK.** Watchers print nothing when healthy; empty output sends nothing.
- **Alert on top.** Deviations are the first line, with a plan B.
- **Controller ≠ worker.** Review/oversight runs on a different model than execution.
- **Cheap for robots, smart for the boss.** Cron/templated/aux work burns the cheap provider; the principal conversation keeps the smart model.
- **Agents cannot fix themselves from inside.** Self-healing is an external process's job.
- **Sanitized.** No private IPs, keys, personal data, or infrastructure topology in this repo. All examples are cleaned.

## License

MIT for code (see `LICENSE`). Documentation is licensed under CC-BY-4.0.
