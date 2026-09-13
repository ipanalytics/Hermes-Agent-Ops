# 11 — domain-persona-packs

_Русская версия: [README.ru.md](README.ru.md)_

**Copy-paste professional roles for agents: chef with inventory, doctor with a limits file, analyst with sources — a role in 10 minutes, not a week.**

> The multi-role skeleton (`04-role-profiles`) is the engine; these are the
> cartridges. Each pack = SOUL.md sections + config pins + file bridges +
> boundaries — filled in and anonymized from roles that run daily.

## The packs (growing)

### Chef — pantry inventory, verified recipes, medical limits read from a file
- SOUL: cooking style, exact measurement rules (salt in precise amounts per step — "to taste" does not work), readiness by physical cues (color, crust, liquid) not minutes.
- Data: inventory file ("currently in stock — to finish" vs "not on hand"), verified-recipe list with status markers `[VERIFIED]` / `[PRINCIPLE]` / `[NEW]`, equipment quirks.
- Boundaries: never improvise around the doctor's file; recipes only from the approved list unless the human says otherwise.
- Bridges: reads the doctor's limits file before every plan (salt, allergens); writes leftovers into inventory after each meal.

### Doctor — medications and supplements; answers only when asked, writes the schedule file
- SOUL: no diagnoses beyond scope, no dosages improvised; writes the limits file the chef reads; updates the schedule file on changes only.
- Data: limits/schedule file (shared), supplements state.
- Boundaries: referral language when out of scope; never spams — updates only on change.

### Analyst / operator — periodic sweep on a separate model
- SOUL: reviewer ≠ worker; sweep brief self-contained (see `05`); output one line when normal, 🔴 per incident; schedule-aware freshness; deliberate exclusions.
- Boundaries: no destructive action without an owner command; report, don't sneak around policy.

## Pack anatomy (what "having a pack" means)

1. `SOUL.md` sections ready to merge into the template from `04`.
2. `config` pins: model tier (cheap/primary), frequency, delivery topic.
3. `bridges/`: the files this role reads and writes, with owners.
4. `boundaries`: gateway ignore-lists + SOUL rule, both layers.
