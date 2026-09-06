# 02 — agent-gateway-supervisor

**External supervisor for an LLM agent gateway: heartbeat-based self-healing, restart with cooldown, and a guard cron that resurrects the supervisor itself.**

## What you get here (real, runnable)

- `gateway_supervisor.py` — the external daemon. Detects: stale heartbeat (process dead/hung) and fresh fatal markers in log tails (the "alive but dead" DB-race signature). Restarts via `--restart-cmd` with cooldown + hourly cap, alerts to Telegram, clears *forgotten* maintenance pauses, escalates to "manual restore needed" instead of ever auto-restoring state.
- `supervisor_guard.sh` — scheduler cron that re-spawns the supervisor if it died (anchored `pgrep`, otherwise the guard matches itself).

## The failure classes it treats

1. **Process alive, bot dead.** The gateway process runs (`ps` fine, heartbeat stale), messages pile up, cron jobs fail. Classic cause: a state-DB sidecar race — every *new* connection is refused while the old holder keeps writing to a deleted WAL.
2. **Process dead/hung.** Heartbeat goes stale.

## Hard-won rules (why it looks like this)

- **Agents cannot heal themselves from inside.** Terminal processes die with the gateway on restart — a self-restarting wrapper never finishes its own cleanup (observed twice). Scheduler jobs that restart the gateway get blocked by policy scanners → the healer must be an external daemon.
- **Watch the watcher.** The supervisor itself can die with a restart → a scheduler-owned guard cron re-spawns it. Fresh supervisor PID after a restart = success signal.
- **Pause before you touch.** `touch pause-file` before manual maintenance; a pause older than ~3 min with no update process running is *forgotten* — the supervisor clears it and alerts.
- **Never auto-restore the DB.** Past the hourly cap it escalates; a robot must not roll back state on its own.
- **Post-restart checklist**: new code head, new gateway PID, heartbeat < 60 s, supervisor alive with a *new* PID, DB integrity OK.

## Why this gets stars

"Process alive but bot dead" is the most frustrating failure mode in agent infrastructure, and the layered watcher design — with the honest note that the watcher is watched because its PID dies on restart — is exactly the detail people star repos for.
