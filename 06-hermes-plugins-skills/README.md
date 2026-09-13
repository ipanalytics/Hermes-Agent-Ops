# 06 — Hermes plugins & skills

_Русская версия: [README.ru.md](README.ru.md)_

**Packaging the proven pieces as Hermes plugins, skills, and cron recipes — and contributing them upstream.**

## What you get

- `skills/one-shot-reminder/SKILL.md` — a complete skill: the zero-LLM-cost fixed-text reminder pattern (script + one-shot no-agent job + auto-disable), with timezone and anchoring pitfalls.
- `cron-recipes/monitor-gated-digest.md` — wake the LLM only when something changed (cheap change-detector gate + continuity dedupe): price watches, release watchlists.
- `cron-recipes/watchdog-chain.md` — keep rootless long-lived services alive via scheduler watchdogs; anchoring and detachment rules from production.

## Design notes

- **Prompts must be self-contained**: a cron job runs in a fresh session with no chat context — everything it needs goes in the prompt or a referenced file.
- **Scripts live as files**, never inline heredocs (policy scanners block them).
- **`no_agent` watchers print nothing when healthy** — empty stdout = zero delivery = zero cost. This one rule makes monitoring nearly free.
- **Test one-shots by firing them manually** before scheduling them for real.
- **Upstream path**: what's generic enough belongs in the Hermes project itself (docs PRs, core features); the rest stays as community plugins. Each packaged piece should note which bucket it is in.

## Why this matters

Hermes has a real open-source audience. A "power-user" pack with battle-tested recipes converts private scar tissue into community value — and brings stars to the parent repo.
