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
ships tests. Measured on a 124-row routing set: 70 unique rows, 29 conflict groups, train-val
input overlap 1 -> 0.

## v0.4.2 — docs and slot measurement
17 model-slot-bakeoff measures candidates for a
slot on real tasks — latency, billed cost per task, the upstream that actually served, a
hidden-test grade, and tool-call support. Fixes a stale module count and directory tree in the
root README.

## v0.5 — reliability and economics
18 harness-probes: JSON-declared acceptance probes, a baseline only `accept` moves, `check` failing
on regression. 19 cost-governance: a cap that pauses the most expensive jobs once a day and resumes
them, cost per successful task per role, and a prompt-vs-toolset audit. 20 task-evals-and-autopsy:
output freshness, size and shape, failure streaks, stuck queues, an error classifier that reports
each new failure once, and a compiled operator brief. 21 blind-spot-audit: a weekly random sample
of accepted output judged against a rubric, reporting the share the checks missed. 22
difficulty-router: tier routing from measured difficulty, with a refusal rule for repins that make
mechanical work dearer per token. 23 research-intake: OAI-PMH harvest, equal-window term counting,
and the journal schema that records adoptions and rejections with reasons. 24 llm-to-script: the
collector-plus-formatter inversion, the shortlist tool, and the measured savings. BENCHMARKS.md
collects the before/after numbers in one place. Every module in this release ships tests (40 checks
across the seven).

## v0.6 — watching the estate
25 querylog-domain-scout, 26 ecosystem-map, 27 research-scout, 28 digest-delivery-health,
29 thinking-layer-cost, 30 schedule-audit, 31 compaction-effect-check, 32 routing-outcomes.
Eight modules that watch the work rather than do it: feeds and logs read deterministically,
gated so a quiet week stays silent, a live estate map, delivery health, the reasoning layer's
own cost, and the measurements behind off-peak moves, compaction policy and model pinning.

## Next
- v0.7 — test suites and CI for 01, 02, 07, 09, 10, 14 (the unfinished half of v0.4), plus a CI job
  that runs every module's tests on push.
- v0.7 — live demo data: anonymized sample usage DB plus the dashboard rendered from it.
