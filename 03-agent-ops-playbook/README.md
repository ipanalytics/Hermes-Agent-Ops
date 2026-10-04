# 03 — agent-ops-playbook

_Russian version: [README.ru.md](README.ru.md)_

**The pattern book: what actually breaks when LLM agents run 24/7, and the patterns that fix it.**
Written from production incidents of mine, not from theory. This is the heart of the repository: the
tools come and go; these patterns are my accumulated scar tissue. Anyone running an agent non-stop lands
here on the two things that matter — what will break, and what to do about it.

A few terms for someone new to this stack. **Hermes** is the home AI agent I run on a server of mine —
it ticks through routine jobs on a timer, watches prices, watches its own health, and writes the small
scripts it needs. An **LLM** (*Large Language Model*) is the AI Hermes talks to; each call is paid for
in **tokens** at the **provider** that runs the model. A **scheduled job** (often a **cron job**) fires
on a timer without me being there. A **profile** is one role Hermes plays; each carries its own memory
file. **Context compaction** is squeezing an old conversation into a short summary so the model does
not re-read the whole transcript on every turn. The **gateway** ferries messages between me and the
agent.

## What's inside

- `README.md` — this file: the six patterns and the stories that produced them
- `incidents/` — three sanitized autopsies, each shaped as **symptom → evidence → root cause → fix →
  prevention → lesson**
  - `530k-token-session.md` — the silent budget killer (~7× spend, "model got dumb" turned out to be a
    context swamp)
  - `gateway-alive-but-dead.md` — the database-sidecar race that made a live process a dead bot
  - `auto-update-restart-chain.md` — the auto-update that looked fine and silently took the agent down
    for 12+ hours
- `decision-trees.md` — the checklists I run when something looks wrong: "agent slow?", "balance
  dropping?", "digest missing?", "bot dead but process alive?", "duplicated message?"

## Why it exists

Every pattern here is anchored in a concrete failure I actually had. The clearest is the 530K-token
session in `incidents/530k-token-session.md`: a long conversation grew past the compaction threshold,
the compressor could not commit, and it retried in a loop — every retry a paid auxiliary call on the
main provider. The session ate **627 API calls a day** and ~**142 million cache-read tokens a day**
while Hermes told me nothing was wrong. My own estimates said the two-day spend was about **$1.15**;
the provider's balance page said **$8.50** — a ~7× gap, with the surface symptom that "the chat got
more mysterious and slower for days." The companion in `gateway-alive-but-dead.md` is the gateway that
ran as a process but answered nothing: healthy-looking `ps`, fresh heartbeat, messages piling up in
`pending_messages/` because a SQLite WAL sidecar race refused every new write. And
`auto-update-restart-chain.md` is the auto-update that pulled new code but never restarted the
gateways, leaving live processes with partially replaced modules and the agent silent for 12+ hours.

## The six patterns

### 1. Roles and economics — "the boss and the workers"

Hermes has a *principal* (the main chat with me) and a swarm of *workers* (the cron jobs, the templated
tasks, the auxiliary calls). They run on different models, by design. The principal uses the **smart**
model — where my judgement matters and quality is worth paying for. The cron jobs use the **cheap**
model — a templated morning digest does not need a frontier reasoning model. Auxiliary calls
(compression, titles, review, vision) use the **cheapest model that is competent enough** — those
calls do not earn their keep on a grand one.

I estimate upgrades on direct messages (DMs) only. Extrapolating a model's per-token price onto all
auxiliary traffic overstated my real spend by roughly 3× — the bulk of the bill in real traffic is
cache-hit input on long sessions, which providers bill at roughly 1/50 to 1/100 of fresh-input rate. A
controller must not be the same model as a worker: if the controller gets stuck, the worker on a
different provider keeps answering while I sort the controller out.

### 2. Alerting and digest design — silence is success

The default state is **quiet**. An empty delta produces one short line or nothing at all. When
something does change, the message structure is **deviation first, plan B second**: the alert leads
with what went off-spec, and only then with what to do about it. Content digests are verbose; service
deltas are silent.

Deduplication goes through **continuity**: compare today's output with the previous one, send only the
delta. I gate every LLM run behind a cheap change-detector — if there is no diff, the LLM is not
called. The cheapest call in the system is the one I do not make.

### 3. Session hygiene — shrink it before it swallows the session

The single biggest silent budget killer I have is a giant context. The principal conversation resets
on a daily schedule **and** on idle (about **4 hours** of no traffic). What resets is only the history;
memory, profile, skills, and the long-term topic notes all survive — those are the things I want to
keep.

The compaction threshold is tuned so sessions shrink **before** they become unpayable. In my setup the
cap moved from **500K** down to **250K** after the 530K incident — a budgeting rule, not a quality
rule. Auxiliary compression is pinned to a cheap provider so a failed compaction on the main
conversation does not turn into a runaway burn on the same model that should be answering me. Giant
sessions were my #1 silent budget killer and my #1 "model got dumb" cause; both phrases describe the
same underlying fault.

### 4. Multi-role agents without chaos

Hermes has several roles — a doctor, a chef, an ops engineer, others — each with its own profile and
its own memory file. The rule is **one profile equals one `SOUL.md` equals full role memory**. A
role's memory does not leak into another role; a chef reading the doctor's notes is a bug, not a
feature.

Roles communicate through **files, not messages**. The doctor writes a limits file (`limits.md`) that
the chef reads before drafting a meal plan; there are **zero** cross-role pings inside a single turn.
Topic boundaries are enforced twice: at the gateway (the routing layer ignores certain topics from the
wrong role) and at the SOUL level (a hard rule inside the profile: "if this is a medical question,
defer to the doctor"). Specialists run **on demand, never self-answer** — a specialist that prompts
itself into existence is a specialist that is now wrong by default.

### 5. Who watches the watchers

Every watcher I have is watched by a *different* layer that survives the watcher itself. The wallet
guard watches the provider balance; the gateway supervisor watches the gateway's health; the
digest-delivery check watches the cron jobs. None of these watchers live inside the thing they watch —
putting the watchdog inside the gateway would mean the watchdog dies when the gateway dies. That is
why `02-agent-gateway-supervisor` is a separate systemd user unit and not a cron job inside the gateway.

Freshness checks must know the **real schedule** of each job — a Mon–Fri digest not arriving on
Saturday is not an incident. Not everything is supervised, and exclusions are a documented feature,
not an oversight: I keep a one-page list of "intentionally unwatched" items with the reason next to
each. Watchdog-on-watchdog without exclusions is the fast path to a flaky stack that pages itself.

### 6. Voice-input misunderstandings

When I dictate a request to Hermes, the transcription step routinely garbles domain vocabulary — drug
names, recipe ingredients, project codenames, anything that is not in the common news corpus. I treat
every proper noun from a transcript as a **hypothesis**, not as a fact. Before Hermes acts on the
transcript, it cross-checks the named item against my real inventory, recipe list, and project glossary;
if the lookup disagrees, Hermes asks me instead of guessing. Agents hallucinate confidently about the
owner's own pantry — the assistant invents "I see you have sumac" when the pantry has none — and that is
avoidable by treating the transcript as a low-trust input.

## Decision trees

The full checklists live in [`decision-trees.md`](decision-trees.md); I keep them short on purpose
because long checklists get skipped while panicking. The five recurring ones, in the order they usually
bite: when the agent answers slowly (6–10 min) or got dumb, sort the usage table by cache tokens and
look for a giant session with aborted compression commits (`commit_status: aborted`) — that is the
cause 80% of the time, and the right move is to **reset the session; do not blame the provider**. When
the balance is dropping too fast, anchor on the provider's reported balance, exclude top-ups,
attribute by session (one monster session is the usual answer), then check whether auxiliary traffic is
pinned to the main provider. When a digest or cron did not arrive, first check whether it was scheduled
to run today at all (a Mon–Fri job on Saturday is not an incident); then `delivery_error` and
`last_status`; whether the job is paused, disabled, or pinned to a dead model — and remember "alert
only on change" jobs are silent by design. When the bot is dead but the process is alive, heartbeat
age > 5 min means restart; a fresh `deleted … .db-wal` FATAL means restart on the documented recovery
path (and if it repeats, restore from backup after quarantining the damaged DB); pending messages
piling up is the same class — and **never auto-restore the state DB from a robot**. When a reminder or
digest duplicated, distinguish platform ack-timeout warnings from real duplicates; real duplicates are
fixed at the source by continuity.