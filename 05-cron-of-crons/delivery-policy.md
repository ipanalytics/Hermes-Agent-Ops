# Delivery policy — local vs topic vs alert

Decision rules for where a scheduled job's output goes.

| Job type | Deliver | Why |
|---|---|---|
| data collector that only prepares files for a downstream job | local (never message) | the user does not want raw "OK: sleep=78 ready=69" lines; the downstream digest consumes the file |
| real alert / deviation / threshold breach | user's alert topic | first line, big, with plan B |
| content digest (movies, research, peptides) | its topic, verbose cards | the user reads these in the morning/evening deliberately |
| service delta (train status, price watch) with no change | silence or one line | "train is on schedule" every day is noise; deviations only |
| one-shot life/kitchen reminder | user DM, fixed text | no LLM cost: a no-agent job prints the text, auto-disables after firing |

## Implementation notes

- "Local" ≠ "lost": the output is stored with the job's run history; the
  downstream job reads it from there or from the file the collector wrote.
- The origin of a job is the chat where it was created — check the job record,
  never assume "origin" is the user's DM.
- LLM-gated runs: put a cheap change-detector (script or URL diff) in front of
  the LLM job — identical output to the previous tick skips the agent entirely.
- Continuity (the job sees its own previous output) is the cheap dedupe for
  digests: compare, send only the delta.
- Empty stdout from a no-agent script = nothing is delivered = zero cost.
  This is the canonical "watchdog" pattern.

## Alert noise budget

An outage that lasts two hours must produce **~2 messages**, not ~200.
Rule: one alert on the state *transition* into the problem, one on recovery,
plus at most one reminder every 30 minutes while it persists.

- **Transition-only alerts.** A watcher that posts on every poll turns any
  lasting problem into a flood (observed: 30+ messages in 90 minutes from a
  single sick service). Gate each alert on a state file: first sighting posts,
  repeats are suppressed until the state clears or the reminder timer fires.
- **Silent recovery is the norm.** A unit that restarts itself and comes back
  in under a minute needs no alert at all — that is `Restart=on-failure` doing
  its job. Alert on *failed* restart escalation, not on every restart.
- **Reminder, not replay.** If the problem persists past ~30 min, one short
  reminder is useful ("still down"); re-sending the same alert every cycle is
  not.
- **Budgets scale with severity.** A wallet guard fires at most a few times a
  day by design; a supervisor caps itself (e.g. 3 restarts/hour, then escalate
  to a human). If a job cannot bound its own message count, it is not a
  watchdog, it is a pager.
- **The human's topic is a fire channel.** If the alert topic accumulates more
  than a handful of messages a day on a healthy day, the policy is wrong —
  move routine content to digests and keep the channel for transitions.
