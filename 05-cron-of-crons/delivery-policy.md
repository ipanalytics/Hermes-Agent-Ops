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
