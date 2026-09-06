# Who watches whom — the watch table

Rule: **every watcher is watched by a different layer that survives the
watcher.** No self-referential healing.

| Watcher | Watches | Failure it detects | Survives what |
|---|---|---|---|
| external supervisor daemon | gateway | stale heartbeat; fresh fatal marker in log tail ("deleted ... .db-wal") | gateway restarts (detached daemon; re-spawned by guard if not) |
| guard cron (scheduler-owned) | supervisor daemon | supervisor process missing | everything — scheduler-owned, fresh session each tick |
| operator sweep (third model) | all scheduled jobs | disabled/paused drift, delivery errors, stale freshness, artifacts pile-up | its own fresh session each run |
| balance guard (script) | API spend | low balance; daily burn over threshold; names culprit session | scheduler-owned |
| memory consolidation (weekly) | memory bloat/staleness | stale/duplicated entries | survives session resets |
| daily backup job | state DB + configs | consistency of the restore point | scheduler-owned |

## Survival analysis (who lives through a gateway restart)

| Process origin | Survives restart? |
|---|---|
| spawned from the agent's terminal | NO — dies with the gateway (its PID is a child) |
| spawned by the scheduler (cron) | YES |
| external daemon, detached (setsid) | YES (re-spawn by guard as belt-and-braces) |

Design consequence: never rely on an agent-terminal process to finish work
across a restart (an update wrapper that restarted the gateway never finished
its own cleanup — observed twice). Post-restart finishing work belongs to the
supervisor or the scheduler.

## Freshness, schedule-aware

A freshness check must know each job's real schedule, not just "last ran".
Mon–Fri job on Saturday = correct. Weekly job on Tuesday after a Monday
holiday = investigate. Store each job's expected cadence next to its name.

## Exclusions are a feature

Not every domain is supervised (owner may exempt the kitchen, private topics,
etc.). Document exclusions next to the watch table so a future operator does
not "fix" them back into scope.
