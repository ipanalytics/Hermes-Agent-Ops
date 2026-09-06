# Incident: the 530K-token session

**Class:** silent budget killer / "the model got dumb overnight"
**Severity:** ~7x expected daily spend for 48h before detection

## Symptom
- Provider balance dropped ~7x faster than the local estimate predicted.
- The principal chat had been getting slower and "dumber" for days.

## Evidence
- One session: **627 API calls/day**, ~**142M cache-read tokens/day**, context at **~530K tokens** (compaction limit was 1M).
- **11 compression attempts hung for 6–24 minutes each and aborted** (`commit_status: aborted`); every retry was a paid aux call on the *main* provider, and each fresh tool-output append was a cache *miss*.
- Price-map estimate said ~$1.15 for two days; the provider usage page said ~$8.5. Gap ~7x.
- Attribution: token usage table grouped by `session_id`; one row owned the whole burn.

## Root cause
A long-lived conversation grew past the compaction threshold; the compressor could not commit (a user interrupt or new append kept tearing the commit down), so it retried in a loop. Every loop iteration paid full aux price on the main provider. The session was so large that even "cheap" cache hits were 142M tokens/day.

## Fix
1. Find the session (usage table, sort by cache tokens) — not "buy more credit".
2. Reset the session (operator command). Memory/profile/skills survive resets.
3. Lower the compaction threshold so sessions shrink *before* they become unpayable (500K → 250K).
4. Move **all aux calls** (compression, titles, review, goal-judge) to a cheap secondary provider; the main provider is then only burned by actual conversations.
5. Add the balance guard (see `01-agent-wallet-guard`) so a repeat is caught within hours, with the culprit session id in the alert.

## Prevention checklist
- [ ] Aux pinned to the cheap provider
- [ ] Compaction threshold tuned (not "as high as the model allows")
- [ ] Balance guard alerting with session id
- [ ] Daily session reset policy in place (the giant died overnight anyway)

## Lesson
The model wasn't dumber. Its context was a swamp — and the swamp was expensive.
