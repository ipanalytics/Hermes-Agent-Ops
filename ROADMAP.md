# Roadmap

_Русская версия: [ROADMAP.ru.md](ROADMAP.ru.md)_

Shipped releases, each one a working tree rather than a plan.

## v0.1 — skeleton
Folder structure, English docs, sanitized examples.

## v0.2 — first working tools
01 wallet guard and 02 supervisor as runnable sanitized scripts; 03 incidents and decision
trees; 04 role templates; 05 operator brief and watch table; 06 packaged skill and cron recipes.

## v0.3 — tooling and patterns
07 fresh-prompt linter, 09 ops-as-data exporter, 10 cost dashboard. Pattern packs for session
lifecycle (08), persona packs (11), topic routing (12), voice input (13). SERIES.md maps the
threads.

## v0.3.1 — operations hardening
02 rebuilt on systemd (units + polkit grant + update flow, cron guard dropped). 14
agent-data-intake ships. "Alert noise budget" policy in 05. Incident autopsy
auto-update-restart-chain in 03.

## v0.4 — guardrails and optimization
15 agent-tool-guardrails: AST command gate, skill scanner, worktree lanes with an acceptance
gate, two test suites (22 + 16 checks). 16 gepa-skill-tuner: tuner.py, shell-safety example.

## v0.4.1 — dataset dedupe in the tuner
16 collapses duplicate task-set inputs before the train/val split, reports label conflicts,
ships tests. Measured on a 124-row routing set: 70 unique rows, 30 conflict groups, train-val
input overlap 1 -> 0.

## v0.4.2 — docs and slot measurement
Publication meta-commentary removed across the modules: eleven repeated pitch sections, defensive
parentheticals, a roadmap written as narrative. 17 model-slot-bakeoff measures candidates for a
slot on real tasks — latency, billed cost per task, the upstream that actually served, a
hidden-test grade, and tool-call support. Fixes a stale module count and directory tree in the
root README.

## Next
- v0.5 — test suites and CI for 01, 02, 07, 09, 10, 14 (the unfinished half of v0.4).
- v0.5 — live demo data: anonymized sample usage DB plus the dashboard rendered from it.
- v0.6 — community: persona packs, cron recipes, incident autopsies from other deployments.
