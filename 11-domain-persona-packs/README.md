# 11 — domain-persona-packs

_Russian version: [README.ru.md](README.ru.md)_

**Copy-paste professional roles for agents: chef with inventory, doctor with a limits file, analyst with sources — a role in 10 minutes, not a week.**

> The multi-role skeleton (`04-role-profiles`) is the engine; these packs are
> the cartridges. Each pack = SOUL.md sections + config pins + file bridges +
> boundaries, each filled in and anonymized by me from a role that actually runs daily.

## What the words mean (for someone opening this repo for the first time)

Hermes is my home AI agent — a long-running assistant on my own server that does my routines
(digests, price and gear watches, health digests, monitoring its own failures) and writes
scripts for itself. A **role** (or **profile**) is one professional persona that lives on top
of the same bot: the doctor, the chef, the operator, each with its own memory, files and
hard limits. A **SOUL.md** is the master prompt for one role — a long Markdown file that
defines how it thinks, what it knows, what it will and will not do. The **multi-role
skeleton** in `04-role-profiles` is the engine that turns a SOUL.md and a config into a
working role: it lays out which sections every SOUL.md must have and pins a model tier to
each. A **pack** is one of those fully filled-in roles, packaged so I can drop it into a
new deployment and have a working professional in the time it takes to read a file. The
**gateway** is the single entry point that routes each message to the right role based on
which chat topic it arrived in; **boundaries** are the rules that stop one role from
answering outside its competence. **File bridges** are files one role writes that another
reads — doctor writes the limits file, chef reads it before any plan.

## Why these packs exist

Module `04` gives me the engine: a template, a config layout, a routing table. That is what
makes a role **possible**. These packs are what makes a role **fast**: each one is a working
SOUL.md, a working config, a working set of bridges — already shaped from a role that runs
every day in my home, anonymized and shipped here so I don't re-author the chef, the doctor
or the operator from scratch every time I rebuild. The difference matters when I need a
fifth role: with the engine alone, "I want a sommelier" is a week of writing; with the
right pack, it's "drop in the template, fill in the SOUL.md with this pattern, wire it to
the gateway" — ten minutes.

The packs also pin down a pattern I had to learn by running the roles: a role that
improvises its data shape is a role that drifts. The chef pack keeps the inventory file
shape fixed (in-stock, on-hand list, finished list), keeps the recipe list shape fixed
(`[VERIFIED]` / `[PRINCIPLE]` / `[NEW]` markers), keeps the bridge file shape fixed (limits
written by the doctor). That fixedness is what makes the role auditable.

## The packs (growing)

### Chef — pantry inventory, verified recipes, medical limits read from a file

- **SOUL**: how this kitchen actually cooks. Salt is measured in exact amounts per step —
  "to taste" does not work; readiness is judged by physical cues (color, crust, liquid),
  not by minutes.
- **Data**: inventory ("currently in stock — to finish" vs "not on hand"), a verified-recipe
  list with status markers `[VERIFIED]` / `[PRINCIPLE]` / `[NEW]`, and quirks of the
  specific equipment (which oven runs hot, which pan needs extra oil). `[VERIFIED]`
  recipes are cooked end-to-end in this kitchen; `[NEW]` recipes never ship without a cook.
- **Boundaries**: no improvising around the doctor's file; recipes only from the approved
  list unless the human says otherwise.
- **Bridges**: reads the doctor's limits file before every plan (salt, allergens) and
  writes leftovers back into the inventory after each meal as entries with a use-by date.

### Doctor — medications and supplements; answers only when asked, writes the schedule file

- **SOUL**: no diagnoses beyond scope, no dosages improvised. The doctor writes the limits
  file the chef reads, and touches the schedule file only when something changes.
  Anything past competence is referral language, not a guess.
- **Data**: the shared limits/schedule file and the current supplements state. Limits
  file is the bridge: salt cap, allergens, off-limits combinations with reasons, in a
  shape the chef can read without knowing any medicine.
- **Boundaries**: out of scope means referral language, and no spam — updates happen on
  change, not on a timer.

### Analyst / operator — periodic sweep on a separate model

- **SOUL**: the reviewer is not the worker; the sweep brief is self-contained (see `05`);
  one line of output when everything is normal, 🔴 per incident; freshness judged against
  the sweep schedule. A worker grading its own output is the blind spot that module `21`
  measures; the operator role is the answer — different eyes, the same evidence.
- **Boundaries**: no destructive action without an owner command; report what the policy
  blocks, do not sneak around it.

## Pack anatomy (what "having a pack" means)

1. `SOUL.md` sections ready to merge into the template from `04`. The merge is
   structural: filled in and obeying the template's section order, so the gateway's
   role-loader drops them in without rewrite.
2. `config` pins: model tier (cheap/primary), frequency, delivery topic. Each role carries
   an explicit model pin, not a default — chef on cheap, doctor on careful, operator on a
   third reviewer.
3. `bridges/`: files this role reads and writes, with owners. Each bridge file has a
   declared owner, a reader list and a shape. Bridges without owners drift; bridges with
   owners stay fixed.
4. `boundaries`: gateway ignore-lists + SOUL rule, both layers. The gateway ignore-list
   is the hard wall; the SOUL rule is the soft wall. Both walls are needed; either alone
   has holes.

## Related

- **04-role-profiles** — the engine these packs plug into. The template, the routing
  table, the boundary rules.
- **05-cron-of-crons** — the operator's sweep brief is generated from this module's
  job list, so adding a pack often means adding a scheduled sweep alongside it.