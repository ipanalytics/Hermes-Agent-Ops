# 04 — role-profiles

_Russian version: [README.ru.md](README.ru.md)_

**Multi-role agent architecture on a single gateway: one bot, N professional personas, each with its own memory, topic, and boundaries.**

I run several professional roles on top of one bot instead of paying for and maintaining N separate agents. A *profile* is one persona — a chef, a doctor, an operator — with its own memory file, its own chat topic and its own hard limits. A *gateway* is the single entry point that receives every message and routes it to the right profile. This folder holds the templates that make such a profile self-contained: a master prompt skeleton, a per-role configuration block, and the routing rules that decide who gets what.

## Why it exists

I had been running a single agent and stuffing it with instructions: cook for me, watch my health, monitor the system, draft documents. Every time I added a new role I had to also widen what the model was allowed to do, and every widening eroded the limits that mattered. The doctor instructions and the chef instructions bled into each other in the same conversation, and the operator started offering me recipes at 03:00 because it was bored. I needed separation that the model would actually respect — not a paragraph saying "stay in your lane", but a memory file the role can only read, a topic it can only see, and a config that pins which model sits behind it.

Two facts made the architecture settle. First, one profile = one `SOUL.md` (master prompt), one set of recipe/state files, one chat topic. The whole world of a role lives in that one file; the agent loads it as its persistent identity on every session. Second, the *gateway* — the bot that talks to me — runs the routing logic and never lets the wrong role see the wrong message. Inside the gateway, the routing rules are short tables of "who does what", and the role's own SOUL is just data the role reads when it spins up. A role with its own gateway would answer by itself; I keep them all behind one gateway so the coordinator stays in charge.

The result is what I wanted: a doctor that cannot, by configuration, see my kitchen recipes; a chef that cannot, by SOUL rule, give me a dosage; an operator that runs at 05:00 UTC on a third model (the reviewer is not the worker); an aux pipeline on the cheapest capable provider for compression, titles, and review. Each role pays only for what it does, and none of them knows the others exist.

## What "role", "profile" and "gateway" mean here

- **Role.** A professional purpose the agent serves: cook, doctor, operator, coordinator. Each role has its own voice, its own working memory, its own list of things it must never do.
- **Profile.** The files that make a role runnable: a `SOUL.md` (master prompt), a `config.yaml` block (which model, which provider, which topic, how often it compacts), and the data files it owns (recipes, inventory, schedules, lab results).
- **Gateway.** The single Telegram-style bot that receives every message. It runs routing, ignores out-of-scope topics per profile, and dispatches work to the right role on demand.

The shape is "one bot, N profiles, one routing table". When the human sends a message, the gateway classifies it and either answers as the coordinator or hands off to a specialist profile by spawning a worker session. The specialist does not see the conversation; it gets a self-contained command and returns a compact result.

## What's inside

This folder holds the templates and the routing rules — not the secrets, not the topics, not the SOUL text of any specific role. The point of shipping templates is that every new role gets the same shape; the point of shipping the routing rules is that I (and anyone reading this) can see who decides what.

- `template/SOUL.md.example` — annotated master-prompt skeleton. The section list makes a role self-contained: working style, preferences, measurement rules, inventory, equipment, verified recipes with status markers, **hard boundaries**, historical mistake-protection, voice-pitfall notes. The annotation explains each section so a new role author does not have to guess what belongs where.
- `template/config.yaml.example` — per-role model pinning. Cheap models for workers, a careful model for the doctor, a *third* model for the operator (reviewer ≠ worker), aux calls on the cheapest capable provider, session hygiene, compaction settings. The pinning is the cheapest place to enforce "this role never pays for a smart model unless it needs one".
- `docs/routing.md` — the "who does what" decision table + handover protocol + deliberate exclusions. The table is short on purpose; routing by meaning, not by keyword lists, is what keeps it from going stale.

## The rules that make it work

These five rules are the load-bearing ones. They look like a list of slogans; the value is in the operational discipline behind each.

1. **One profile = one SOUL.md.** The role's whole world lives in one master prompt + its own data files (recipes, inventory, schedules, limits). No scattered context, no "see also" pointer to another file. The agent loads SOUL.md as its persistent identity on every session, and that file alone tells it what it knows and what it must never do.
2. **Roles talk through files, not messages.** The doctor *writes* a limits file (e.g. "max caffeine per day", "no alcohol with this medication"); the chef *reads* it before every plan. Questions go one line into a queue file the other role drains. Zero cross-role pings, full audit trail: every cross-role interaction is a file edit, every file edit has an mtime, and the mtime list is the receipt.
3. **Boundaries are enforced twice.** Once at the gateway level, where the role literally cannot see the private topic (the gateway maintains an ignore-list per profile). And once in the SOUL file, where an explicit rule states plainly: "you are not a medic; no diagnoses, no dosages; you reference the limits file written by the doctor role and never improvise around it". Two layers because the gateway enforces "I never receive the message", and the SOUL enforces "even if I somehow did, I would refuse".
4. **Specialists don't self-answer.** They run on demand through the coordinator. A profile with its own gateway would answer by itself, and that profile would not consult the coordinator when in doubt. I only enable that mode when needed (and I have not needed it yet).
5. **Latest message wins.** When the human contradicts old SOUL data, the new instruction takes priority and is recorded in the SOUL so it is not re-litigated. The agent is a listener, not a debater; if I say "actually I take my coffee stronger now", that overwrites the old line and the next session does not ask again.

## Walkthrough: what `SOUL.md.example` covers

The skeleton has nine sections. Each earns its place by answering one question the role would otherwise have to ask on every session.

1. **HOW TO WORK WITH ME.** The format the role uses when I am mid-task: short verdict, what to do right now, next steps in order, quantities, heat, time, readiness signs (physical cues, not just minutes), what can run in parallel, what NOT to do right now, and how to rescue a mistake. Roles that do not know this format default to paragraphs, which waste my attention when I want a quick decision.
2. **MY PREFERENCES.** Specific likes and dislikes, formatting rules, voice-pitfall notes. "Bold, savory, crusty" beats "I like good food" every time; "do not suggest rare ingredients without need" beats "be practical".
3. **HOW I MEASURE.** Units I actually use, plus the working proportion and the correction knob. The example rule: salt is given by exact amount per step, including "do NOT salt here" — because "to taste" does not work with my blood pressure.
4. **INVENTORY & SOURCES.** Where I shop, staples usually on hand, the current stock to finish, the items I do not have right now and what to substitute. An out-of-stock ingredient should first get a simple substitution; only then should the role suggest a rare alternative.
5. **EQUIPMENT.** What each piece is good at and what it must not be used for. A pressure cooker is good for beans, bad for delicate sauces; the role knows this because the file says so.
6. **APPROVED / VERIFIED RECIPES (do not reinvent).** Each recipe is one line with a status marker: `[VERIFIED]` means the proportions were confirmed by me in real use; `[PRINCIPLE]` means the numbers were lost and the role never invents — only with my confirmation; `[NEW]` is a first run that flips to `[VERIFIED]` only after I report back.
7. **HARD BOUNDARIES.** Domain lines the role must not cross, and what it does when a question is out of file scope (writes one line into a queue file for the other role, tells me "will confirm with <role>", does not guess, does not spam me).
8. **HISTORICAL PROTECTION.** One line per past mistake and the rule that prevents it. The example: "Salt in egg marinade: the marinade is SUGAR 1 tbsp, NO salt — I once confused the two; warn explicitly in every such recipe." Also: voice-input pitfalls (transcription garbles specific terms), with the rule that transcript names are hypotheses to be verified against inventory.
9. **OPERATING NOTES.** Where this role reports back (its topic), what model tier it is allowed to use, anything the coordinator must know to route to it. The coordinator reads this section when it is about to delegate.

The footer is a one-line reminder: "Keep this file tight. Every line earns its place: preference, rule, inventory fact, or mistake-prevention. Bloat dilutes the role." A SOUL.md that drifts into prose becomes the same single-agent problem I was trying to escape.

## Walkthrough: what `config.yaml.example` pins

Per-role pinning is where most of the cost discipline lives. The example config does five things.

- **Coordinator**: the smartest model I can afford, on the primary provider. This is the model that talks to me directly and decides who else to call. It earns its keep because a wrong routing decision wastes every downstream call.
- **Coder**: a worker model on the primary provider, with sandbox = `proot` (a userspace sandbox, so a bot can run shell commands without root). The coder is cheap because it produces machine-checkable artifacts (git commits, passing tests), where "looks plausible" is cheap to detect.
- **Chef**: a cheap flash model on a secondary provider, with a large context window. The chef's context is dominated by SOUL + inventory + recipes, so context window matters more than model rank; the cheapest capable model is fine.
- **Doctor**: a careful, full-size model on the primary provider, low frequency. The doctor only fires on demand (a health question, a lab PDF), and I want the most careful model I have when it does. Frequency is low so cost is bounded.
- **Operator**: a *third* model on a secondary provider, scheduled daily at 05:00 UTC, delivering to a Telegram ops topic. The reviewer must not grade its own work, which is why the operator is on a different model from the coordinator and the coder. Schedule `0 5 * * *` is a daily sweep, not a reactive monitor.

The `aux` block pins the cheapest capable provider for compression, titles, review, vision — the calls that do not need a smart model but must not be free. The `session_reset` block sets the daily+idle reset (mode: both, at 02:00 UTC, idle 240 min, notify false). The `compression` block sets a `threshold_tokens: 250000` cap so context shrinks before it becomes unpayable. None of this is novel; the point is that it is in one place per profile and that adding a profile means adding one block, not editing five.

## Walkthrough: how `docs/routing.md` decides

The routing table is six rows. I keep it short on purpose — routing tables that list every keyword go stale fast, and the coordinator ends up paying the agent to second-guess itself. The rule is: route by meaning, not by keyword lists. When in doubt, the coordinator keeps the message and asks me.

| Signal in the request | Route to | Because |
|---|---|---|
| code, scripts, panels, debugging, "automate this", infra scripting | coder | sandbox + git discipline live there |
| food, recipes, dishes, groceries, "what to cook", meal plans | chef | owns inventory + verified recipes |
| health, meds, supplements, lab results, dosing questions | doctor | owns limits + schedules; chef defers to it |
| "check the system / crons / anomalies", incident review | operator | third model, scheduled sweep, not for ad-hoc chat |
| anything else: research, purchases, documents, bureaucracy | coordinator | default owner |
| a complex multi-step task | think first, then execute | plan on a full model, execute on flash |

The handover protocol is the second half of the file, and it is the part that keeps multi-role from turning into multi-noise:

1. Classify silently.
2. Hand to the role with ONE self-contained command: `run <role> with "<task + full context>"` — the role does not see the conversation.
3. Return the result to me, compactly. Never forward raw role output; the role's voice is not mine and I do not need its scaffolding in my chat.
4. Record who did what and the outcome (status line).
5. Status: where the role reports back (its topic) vs where I talk.

The exclusions section is short and deliberate. Some domains are explicitly NOT supervised by the operator (the chef's kitchen is one of mine — a documented choice, not an oversight). Private topics (where the coordinator and I talk) are excluded at the gateway level for every other role (ignore list) AND in the role's own SOUL.md. Two layers, same reason as the boundaries rule above.

## What this gives me in practice

- **Cost discipline by construction.** The cheapest model I trust handles the calls that do not need a smart one. The smart model only answers the chat that reaches the coordinator.
- **Audit trail by construction.** Every cross-role interaction is a file edit. Every file edit has an mtime. The mtime list is the receipt.
- **Failure isolation by construction.** A bad prompt in the chef profile does not bleed into the doctor profile; a doctor profile that hallucinates does not poison the operator's daily sweep.
- **Privacy by construction.** The role literally cannot see the topic it is not routed to; the SOUL reinforces the rule.

The setup cost is real: one `SOUL.md` per role, one config block per role, one routing table to maintain. The payoff is that the architecture does not need to be re-justified every time I add a role, and the limit on what each role is allowed to do is encoded in two places that have to fail simultaneously for the limit to be violated.

## Directory structure

```
04-role-profiles/
├── README.md
├── README.ru.md
├── docs/
│   └── routing.md             # decision table + handover protocol + exclusions
└── template/
    ├── SOUL.md.example        # annotated master-prompt skeleton (9 sections)
    └── config.yaml.example    # per-role model pinning + session hygiene + compression
```

## Use cases

- A single Telegram-style bot that hosts several professional personas on different chat topics, with the coordinator deciding who is asked.
- Anyone who has outgrown a single-agent prompt and needs memory + limits that do not bleed across domains.
- A setup where different roles need different models (cost, capability, or separation of duty).
- Privacy-by-construction: a role that should not even see the existence of another topic.

## Limitations

- A role profile is not a substitute for a real specialist. The doctor role respects the limits file but does not replace a doctor.
- The architecture depends on the gateway's routing table being kept short and meaningful. A long, keyword-based routing table goes stale and routes wrongly; the value of "route by meaning" is that it survives minor rewordings.
- SOUL.md is a Markdown file. It drifts. The discipline of "tight file, every line earns its place" is on me, not on the tool.
- The third-model operator pattern (reviewer ≠ worker) costs an extra provider relationship. It is worth it for me; for someone who only has one, it is overhead.
- Boundaries are enforced twice, but the second enforcement (the SOUL rule) is a string the model reads. The gateway is the real enforcement; the SOUL is the safety net.

## Disclaimer

This folder ships templates and a routing table. It does not ship secrets, topics, SOUL text, or configuration — every real deployment pins its own models, providers, schedules, and boundaries. Use the examples to configure the next role, not to copy an existing one.