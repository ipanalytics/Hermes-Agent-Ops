# Incident: the auto-update restart chain (state DB swap under live processes)

**Class:** update/restart orchestration failure
**Severity:** full agent outage (intermittent 12+ h); data-intake receiver dead; one health reading delivered 12 h late but not lost

## Symptom
- An automatic update pulled new code but **did not restart the running gateways** (log: "A previous hermes update pulled new code but did not restart running gateways / mixed sys.modules"). Old processes kept running with partially replaced modules.
- The state DB file was **replaced/swapped while live processes still held it open** (including `-wal`/`-shm` sidecars). Hermes detected the swap, halted writes, and diverted messages to `sessions/*.jsonl` and `pending_messages/pending-*.json`.
- The active DB then tested **malformed** (`database disk image is malformed`).
- The gateway was being managed by **two systems at once**: systemd (`gateway run`) and a self-written watchdog (`hermes gateway restart`). systemd saw "Gateway already running (PID …)" and entered `failed` after ~8 attempts.
- The watchdog's hung `hermes gateway restart` process held `state.db`, `-wal`, and `-shm` open through several file descriptors for hours. New sessions could not write; cron jobs failed with "session storage could not be written".
- Systemd showed a partial picture: other live instances kept running inside transient cron scopes (`hermes-worker-cron-*.scope`), invisible to `systemctl`.

## Evidence
- 94 × "unable to open database file" in one day, first occurrence 01:01, waves every few hours, hard failure 13:32–14:21.
- `PRAGMA quick_check` on the live DB: `ok` after restore — the corruption was introduced by the swap, not by normal operation.
- Health-intake receiver (separate process, kept alive only by a cron watchdog *inside* the gateway) died in the same window and stayed dead for ~12 h because its lifeline was gone with the gateway.
- Device-side log: `Webhook failed; queued locally: Connection refused` at 05:08, retried every ~17 s, delivered 15:15 the moment the receiver came back. Zero data loss, 12 h latency.

## Fix
1. Stop **all** gateway/dashboard/cron instances (including transient scopes — `ps`/`pgrep`, not `systemctl` alone).
2. Restore the state DB from the last clean daily backup (quarantine the malformed one, do not delete).
3. Restart only through systemd units. Verify: one gateway PID, fresh heartbeat, no stray scopes.
4. Re-verify data intake end-to-end (synthetic POST through the TLS proxy → row in SQLite).

## Why not "just re-run the update"
The update tool treats a running dashboard as "manual-serve" and re-spawns it in a transient cron scope — the same class of mistake that caused the incident. Update must stop the dashboard first and restart components only via systemd (`02-agent-gateway-supervisor/scripts/hermes-update-run.sh`).

## Prevention
- **One owner per process:** supervision and restarts only through systemd units; `hermes gateway restart` is banned from watchers and update flows.
- **Independent supervisor:** the gateway supervisor runs as its own systemd user unit (not a cron job inside the gateway) — no circular dependency (`02-agent-gateway-supervisor/systemd/supervisor.service`).
- **Independent intake:** health receivers are systemd user units with `Restart=on-failure` and multi-threaded servers; device readings spool locally and retry until delivered (`14-agent-data-intake`).
- **Post-update check:** heartbeat + unit-state verification with ✅/❌ report, plus a silent insurance check ~30 min after the update window and again before the morning reports.
- **Alerts on transitions:** one alert per incident state change, not per poll — a 12 h outage must produce ~2 messages, not ~200.

## Lesson
The update that looks fine on the surface is the highest-risk operation in the system. Update = stop everything you manage → replace code → restart only through the one owner (systemd) → verify heartbeat, units, and an end-to-end write. Anything less silently trades today's uptime for tomorrow's incident.
