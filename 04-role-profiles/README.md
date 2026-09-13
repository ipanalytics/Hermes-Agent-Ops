# 04 — role-profiles

_Русская версия: [README.ru.md](README.ru.md)_

**Multi-role agent architecture on a single gateway: one bot, N professional personas, each with its own memory, topic, and boundaries.**

## What you get

- `template/SOUL.md.example` — annotated master-prompt skeleton: the section list that makes a role self-contained (working style, preferences, measurement rules, inventory, equipment, verified recipes with status markers, **hard boundaries**, historical mistake-protection, voice-pitfall notes).
- `template/config.yaml.example` — per-role model pinning: cheap for workers, careful for the doctor, a *third* model for the operator (reviewer ≠ worker), aux calls on the cheapest capable provider, session hygiene + compaction settings.
- `docs/routing.md` — the "who does what" decision table + handover protocol + deliberate exclusions.

## The rules that make it work

1. **One profile = one SOUL.md.** The role's whole world lives in one master prompt + its own data/recipe files. No scattered context.
2. **Roles talk through files, not messages.** Doctor *writes* a limits file; chef *reads* it before every plan. Questions go one line into a queue file the other role drains. Zero cross-role pings, full audit trail.
3. **Boundaries are enforced twice**: gateway-level topic ignore-lists (a role literally cannot see the private topic) + an explicit SOUL rule ("you are not a medic; no diagnoses").
4. **Specialists don't self-answer.** They run on demand through the coordinator. A profile with its own gateway would answer by itself — only enable that when needed.
5. **Latest message wins.** When the human contradicts old SOUL data, the new instruction takes priority and is recorded so it isn't re-litigated.
