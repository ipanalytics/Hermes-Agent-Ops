# 08 — session-housekeeping

**The memory and session lifecycle toolkit: tame the 2.5K-message session, keep memory lean, and never lose a fact worth keeping.**

> The pattern behind it: **three tiers** — sessions (ephemeral, reset daily), memory (small,
> injected into every turn, must stay tight), skills (procedural knowledge, loaded only when
> relevant). Most setups keep everything in one giant session until it becomes a swamp — slow,
> expensive, "the model got dumb". The model didn't get dumb. The swamp got big.

## The tiers

| Tier | What lives there | Lifecycle |
|---|---|---|
| **Sessions** | conversation history | reset daily + after ~4 h idle; everything survives except history |
| **Memory** | who the user is, standing conventions, environment facts | hard char budget; weekly consolidation |
| **Skills** | procedures, pitfalls, domain playbooks | loaded on demand per task type; updated after hard tasks |

## The housekeeping jobs (copy-paste)

### 1. Session librarian (on demand)
Prompt-driven session ops: find a session by topic, rename, archive, prune the fat.
When the "big session" crosses the pain threshold (slow, costly, dumb), the fix is a
**reset** — memory/profile/skills survive it, so nothing of value is lost.
One-shot command: "reset me cleanly, archive the last hour if needed, continue."

### 2. Memory consolidation (weekly cron, cheap model)
A scheduled pass over memory that applies the rules:
- fact stale within a week → belongs in session history, not memory
- procedure/pitfall → belongs in a skill, where it loads only when relevant
- duplication across entries → merge (memory is injected into EVERY turn — bloat is a tax on every single message)
- imperative self-instructions ("always answer in X") → rewrite as declarative facts
  ("user prefers X"), so they can't override a fresh instruction

### 3. Compaction tuning (infra)
Sessions shrink *before* they become unpayable: threshold in the low hundreds of K tokens,
aux calls (compression) pinned to the cheap provider. A 530K-token session that retries a
failing compression is how a calm week becomes a 7x bill (full story in
`03-agent-ops-playbook/incidents/530k-token-session.md`).

## Deliverable notes

- Everything here is configuration + prompts, no heavy code — that is the point.
- The working contract is the three-tier table and the rules above; the
  example prompts and config snippets live next to this README as they are
  generalized from running setups.
