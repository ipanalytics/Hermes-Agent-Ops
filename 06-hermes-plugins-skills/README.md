# 06 — Hermes plugins & skills

_Russian version: [README.ru.md](README.ru.md)_

**The pieces of my home-agent setup that survived real production, packaged so they travel — and contributed upstream where they belong.**

Hermes is my home AI agent: it lives on my own server, runs on a schedule, takes care of its own routine (digests, price and tech watches, health, monitoring of its own failures), and writes its own scripts. Over time it has accumulated a small library of patterns that have been paid for with real incidents and now just work — patterns for fixed-text reminders, for digest jobs that should not pay for a model when nothing changed, for keeping long-lived services alive when the host has no root rights. This folder packages three of those patterns as ready-to-use pieces of a fresh Hermes deployment.

The vocabulary matters, because anyone landing here is not assumed to be familiar with Hermes yet:

- A *plugin* is a directory under Hermes' plugins directory that extends the agent — extra commands, extra tools, extra scheduled jobs.
- A *skill* is a self-contained markdown pack with YAML metadata: name, description, version. The agent loads it on demand when the description matches the task. Skills teach the agent *how to do* a thing; they do not add new code.
- A *cron recipe* is a written-down pattern for a scheduled job (a "cron job"), meaning a task that fires at a fixed time and runs on its own. Each recipe in `cron-recipes/` is one such pattern, named and minimal.
- An *LLM* (large language model) is the AI that processes the text — the thing that costs *tokens* (paid pieces of text, roughly one word each).
- A *prompt* is the instruction text that the LLM gets fed when the job fires.
- A *fresh session* means the agent starts from no memory of any past chat — every cron job is a fresh session, which is why every prompt has to be self-contained.
- A *gate* is a cheap filter that decides whether the LLM is woken at all on a given tick.
- A *provider* is the company or gateway that actually serves the model when I send a request.

## Why it exists

A recipe that survived real production is worth more than a fresh one. Once a piece has been paid
for with real incidents — timezone pitfalls that fired reminders at the wrong hour, watchdog
detachments that left a service dead for an hour, silently burning LLM (large language model)
costs on a digest that ran every ten minutes to ask the same nothing — leaving that recipe buried
in my own folder wastes it. When I package it, the experience becomes something anyone can reuse,
and the generic parts belong in the Hermes project itself rather than in my private setup.

The other half is the open-source audience. Hermes has a real community. My "power-user" pack with
battle-tested recipes turns my private scar tissue into community value, and brings stars to the
parent repo.

## What's in the folder

- `skills/one-shot-reminder/SKILL.md` — my complete skill for zero-cost reminders: a fixed-text
  bash script runs on a one-shot scheduled job with no agent and no model call, delivers its
  stdout verbatim, then disables itself. The skill carries the timezone and anchoring pitfalls
  that bit me (Berlin lives in Europe/Berlin, UTC+2 in summer, so a "17:30 evening reminder" is
  `15:30` in UTC).
- `cron-recipes/monitor-gated-digest.md` — my recipe for waking the LLM only when something
  changed. A cheap change-detector runs first (a script or an HTTPS endpoint that returns a
  deterministic string); when the string is identical to the previous tick the run is silent and
  costs zero tokens; when the string differs, the LLM wakes with the diff injected into the
  prompt. Price watches, release watchlists, any "tell me only when something actually moved"
  digest.
- `cron-recipes/watchdog-chain.md` — keeping long-lived services alive without root rights via
  scheduler watchdogs. The watchdog script checks a port or a process; if dead, restarts the
  service detached via `setsid` and prints an alert; if healthy, prints nothing. Anchoring and
  detachment rules from production.

## Design notes

- **Prompts must be self-contained**. A cron job runs in a fresh session with no chat context —
  everything it needs goes in the prompt or in a referenced file. Preferences, thresholds,
  anti-keywords — all in the prompt.
- **Scripts live as files**, never inline heredocs. Policy scanners block heredocs, and the
  script needs to be version-controlled separately from the job that runs it.
- **`no_agent` watchers print nothing when healthy**. Empty stdout = zero delivery = zero cost.
  This one rule is what keeps my monitoring bill near zero: a watchdog that only speaks when
  something is wrong turns a once-per-three-minute job into a free one.
- **I test one-shots by firing them manually** before scheduling them for real. The first time
  a one-shot runs should not be at its real target time.
- **Upstream path**: what's generic enough belongs in the Hermes project itself (documentation
  PRs, core features). The rest stays as community plugins. I note in each packaged piece which
  bucket it is in.

## How a recipe becomes a skill or a cron recipe

When a pattern repeats and bites me twice, I lift it out of the script where it was born, give it a
name, write down the failure mode that made me need it, and put it where the next fresh deployment
will find it. The folder is not a backlog of every clever thing Hermes has ever done — it is the
short list of patterns that turned a real failure into a non-event the second time around. Anything
that has not yet failed twice stays in the deployment that produced it.

## Directory structure

```
06-hermes-plugins-skills/
├── skills/
│   └── one-shot-reminder/SKILL.md
└── cron-recipes/
    ├── monitor-gated-digest.md
    └── watchdog-chain.md
```

## Related

- **02-agent-gateway-supervisor** — the external supervisor the watchdog chain defers to for
  services that are not safe to restart from a scheduler job.
- **04-role-profiles** — how I tell the agent which skill packs are loaded by default.
- **07-fresh-prompt-linter** — the lint that catches prompts which assume an environment that is
  not there (chat history, tools, files).

## License

Apache 2.0 — see the repository LICENSE.