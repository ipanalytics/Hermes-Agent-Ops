# Decision trees — the checklists we actually run

## "The agent answers slowly (6–10 min) or got dumb"

1. Is a giant session live? Check the usage table for one session with hundreds of K tokens and aborted compression commits (`commit_status: aborted`). → That is the cause 80% of the time. **Reset the session.** Do NOT blame the provider.
2. Provider rate-limiting/truncation? Look for `429`, `RateLimitError`, "stream stale" in the error log. → Route-level issue; not fixable by retuning config.
3. Compaction actually hanging? (telemetry shows multi-hundred-K ms durations). → Lower threshold, move aux off the main provider.
4. Session/model drift? A job pinned without a date suffix may have silently moved to a weaker snapshot or a fallback model. → Pin with suffix, check fallback flags.
5. Nothing above → check the aux calls (compression/title/review) — they may have inherited the main provider and a *giant* context.

## "The balance is dropping too fast"

1. Anchor: real provider balance this morning vs now (not the price map).
2. Top-up detected? Re-anchor (refills are not burn).
3. Attribute by session: usage table, sort by cache-read tokens. One monster session? → reset it, lower compaction threshold.
4. Aux on main provider? → pin to cheap secondary.
5. Cron jobs on the *smart* model? → template work belongs on the cheap model ("cheap for robots, smart for the boss").

## "A digest/cron didn't arrive"

1. Was it scheduled to run today? (Mon–Fri job on Saturday is not an incident.)
2. Delivery error in the job record? (`delivery_error` / `last_status`)
3. Job paused? Enabled? Pinned to a dead model/key?
4. Silent-by-design? If the job is "alert only on change", an empty day is a SUCCESS — check the last run timestamp, not the absence of a message.

## "The bot is dead but the process is alive"

1. Heartbeat age > 5 min? → restart.
2. Fresh `deleted ... .db-wal` FATAL in logs? → restart on the documented recovery path; if repeated, restore from backup (quarantine first).
3. Pending messages accumulating? → same class; fix the writer, then flush.
4. Never auto-restore the DB from a robot. Escalate.

## "A reminder/digest duplicated"

1. Delivery ack-timeout warnings in the log are usually noise from the platform's ack semantics — check whether the user actually received two messages before "fixing" anything.
2. Real duplicates → dedupe at the source (continuity: compare with previous output, send only the delta).
