# 08 — session-housekeeping

_Russian version: [README.ru.md](README.ru.md)_

My memory and session lifecycle toolkit. A "session" is one running conversation with the agent;
left alone it grows until it is slow and expensive, and the fix is knowing what to keep where.
This is how I keep a multi-thousand-message session workable, memory (the small text the agent
sees on every turn) lean, and every fact worth keeping in the layer where it belongs.

> The pattern behind it: **three tiers** — sessions (ephemeral, reset daily), memory (small,
> injected into every turn, must stay tight), skills (procedural knowledge, loaded only when
> relevant). Most setups keep everything in one giant session until it becomes a swamp — slow,
> expensive, "the model got dumb". The model didn't get dumb. The swamp got big.

## What the words mean (for someone opening this repo for the first time)

Hermes is my home AI agent — a long-running assistant on my own server that does my routines
(digests, price and gear watches, health digests, monitoring its own failures) and writes
scripts for itself. A **session** is one running conversation with Hermes, kept in a file on
disk: my question, the agent's answer, my next question, and so on, in order. A **token** is
a small chunk of a word, and every session, every memory file, every model request is
measured in tokens. **Memory** is a small text file that Hermes reads on every turn before
answering; it carries "who is the user, what are the standing rules, what does the
environment look like." **Skills** are Markdown playbooks I keep in a folder, each one a
procedure for a recurring task type, loaded only when the task matches. A **cron** is a
scheduled task. A **provider** is the company that runs the model Hermes talks to; a
**cheap provider** is the one I keep on hand for jobs where a strong model would be a waste.

## Why it exists

A session grows without a limit until it becomes the problem itself: every turn carries the
whole history, every turn gets slower and more expensive, and the quality drop gets blamed on
the model. The 530K-token session that retried a failing compression until my bill went 7x
(`03-agent-ops-playbook/incidents/530k-token-session.md`) is the incident I shaped this
toolkit around. Memory bloat is the quieter version of the same failure: memory is injected
into EVERY turn, so every unnecessary line there is a tax on every single message.

What happened in that incident: a weekly job left unattended filled its session with
530,000 tokens of prior context; Hermes tried to compress that history, the compression call
failed and retried several times, and each retry re-pushed the full 530K through the model.
A week that normally cost a small sum came to seven times as much, with almost no value
added — the session had already passed the point where more context helped. The fix was not
a smarter model or a bigger budget. The fix was to keep sessions short to begin with:
shrink them early, on the cheap provider, before they become unpayable.

## The tiers

| Tier        | What lives there                                            | Lifecycle                                                                |
|-------------|-------------------------------------------------------------|--------------------------------------------------------------------------|
| **Sessions** | conversation history                                       | reset daily + after ~4 h idle; everything survives except history       |
| **Memory**   | who the user is, standing conventions, environment facts    | short hard-char budget; weekly consolidation on the cheap model         |
| **Skills**  | procedures, pitfalls, domain playbooks                     | loaded on demand per task type; updated after hard tasks                |

The hard-char budget on memory matters more than it looks. Memory is not "some text I edit
when I remember." Memory is read into every single request, so a memory file of N characters
costs N characters of input tokens on every turn, for the entire life of the deployment.
A 2 KB memory file means 2 KB of tax per turn; a 200 KB memory file means 200 KB of tax per
turn, on top of the conversation. That is why "tight" is the operating word.

## The housekeeping jobs (copy-paste)

### 1. Session librarian (on demand)

Prompt-driven session ops: find a session by topic, rename, archive, prune the fat.
When my "big session" crosses the pain threshold (slow, costly, dumb), my fix is a
**reset** — memory/profile/skills survive it, so nothing of value is lost.
One-shot command: `reset me cleanly, archive the last hour if needed, continue.`

What that command does, step by step: it tells Hermes to close the current session, archive
the last hour of context into a session-history file, and start a fresh session on top of the
same memory and the same skills. Memory, skills and profile are not touched — only the
conversation history disappears, with a copy of the last hour already on disk. The first
time I did this, the new session answered faster on the first turn than the old one had on
its hundredth.

### 2. Memory consolidation (weekly cron, cheap model)

A scheduled pass over memory that applies the rules:

- fact stale within a week → belongs in session history, not memory
- procedure/pitfall → belongs in a skill, where it loads only when relevant
- duplication across entries → merge (memory is injected into EVERY turn — bloat there is a
  tax on every single message)
- imperative self-instructions (`always answer in X`) → rewrite as declarative facts
  (`user prefers X`), so they can't override a fresh instruction

The last rule is the one that took me the longest to learn. An imperative like
"always answer in German" in memory is a self-instruction: the model treats it as a hard
rule that can override a fresh user request ("answer in English today, I'm translating").
The same fact rewritten as a declarative ("user prefers German") is a preference: it
carries across turns but yields to a fresh instruction. The wording matters, and the
weekly pass is where I keep the wording honest.

The cron runs the consolidation on the cheap provider — the pass is cheap, the model does
not need to be strong, and the file is short. Running consolidation on the primary model
would be paying full price for a janitorial task.

### 3. Compaction tuning (infra)

Sessions shrink *before* they become unpayable: threshold in the low hundreds of K tokens,
aux calls (compression) pinned to the cheap provider. A 530K-token session that retries a
failing compression — how a calm week becomes a 7x bill (full story in
`03-agent-ops-playbook/incidents/530k-token-session.md`).

The threshold matters because of compounding cost: a session at 200K tokens is roughly twice
as expensive per turn as one at 100K, and the cost grows with every new turn. Compressing at
200K keeps the average cost flat; compressing at 500K lets the cost grow roughly linearly
with the session, and a single failed-compression retry is the failure that turned one
weekly incident into a 7x bill. Compression is a mechanical summarization, so the cheap
provider gives no quality loss and a failed strong-model retry is exactly the failure that
started the incident.

## Deliverable notes

- Everything here is configuration + prompts, no heavy code — that is the point.
- The working contract is the three-tier table and the rules above; my
  example prompts and config snippets live next to this README as they are
  generalized from running setups.
- The weekly cron for memory consolidation is a single scheduled prompt plus a file
  rewrite; the session librarian is a one-line command I issue when the pain
  threshold is crossed; the compaction threshold is a single number in config.