# 03 — agent-ops-playbook

_Русская версия: [README.ru.md](README.ru.md)_

**The pattern book: what actually breaks when LLM agents run 24/7, and the patterns that fix it.** Written from production incidents, not theory.

> This is the heart of the repository. Tools come and go; these patterns are the accumulated scar tissue.

## What you get

- `README.md` — chapter outline (the patterns, summarized below)
- `incidents/` — sanitized autopsies, each: symptom → evidence → root cause → fix → prevention → lesson
  - `530k-token-session.md` — the silent budget killer (7x spend, "model got dumb" was a context swamp)
  - `gateway-alive-but-dead.md` — the DB sidecar race that made a live process a dead bot
- `decision-trees.md` — the actual checklists: "agent slow?", "balance dropping?", "digest missing?", "bot dead but process alive?", "duplicated message?"

## Chapters

### 1. Roles and economics — "boss and workers"
The principal conversation runs the *smart* model; cron/templated jobs run the *cheap* one; aux calls (compression, titles, review, vision) run the cheapest capable one. Estimate upgrades on the DM only — extrapolating all traffic overstates cost ~3x. A controller must not be the same model as the worker.

### 2. Alerting and digest design
**Silence = OK.** Empty delta → one short line or nothing. **Alert on top**: deviation first, big, with a plan B. Content digests are verbose; service deltas are silent. Dedupe via continuity; gate LLM runs behind a cheap change-detector (no diff → no LLM call).

### 3. Session hygiene
Daily reset + idle-based reset (~4 h); memory/profile/skills survive; only history resets. Compaction threshold tuned so sessions shrink before they become unpayable; aux compression pinned to the cheap provider. Giant sessions are the #1 silent budget killer and the #1 "model got dumb" cause.

### 4. Multi-role agents without chaos
One profile = one SOUL.md = full role memory. Roles communicate through **files, not messages** (doctor writes a limits file the chef reads before every plan; one-line question queue; zero cross-role pings). Boundaries enforced twice: gateway-level topic ignore-lists + explicit SOUL rule. Specialists run on demand, never self-answer.

### 5. Who watches the watchers
Every watcher is watched by a *different* layer that survives the watcher. Freshness checks must know each job's real schedule. Not everything is supervised — exclusions are a documented feature, not an oversight.

### 6. Voice-input misunderstandings
Transcriptions garble domain terms. Treat every name from a transcript as a hypothesis; cross-check against the user's actual inventory/recipes before lecturing. Agents hallucinate confidently about the user's own pantry — embarrassing and avoidable.
