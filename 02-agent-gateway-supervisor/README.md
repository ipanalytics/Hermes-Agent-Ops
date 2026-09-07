# 02 — agent-gateway-supervisor

**Gateway supervision done properly: systemd owns the processes, one external supervisor detects "alive but dead" states, and a polkit grant lets the unprivileged agent restart its own units. No `gateway restart` from inside the agent, ever.**

Revision 2026-09-07: rebuilt after an incident where the old design (self-written watchdog + `hermes gateway restart` racing systemd) corrupted the state DB and took the whole agent down for ~12 h. The lesson is encoded in the file layout below.

## Files

| Path | What it is |
|---|---|
| `systemd/gateway.service` | system unit for the messaging gateway. `Restart=on-failure`, `RestartSec=10s`, `StartLimitIntervalSec=300/StartLimitBurst=5`, `NoNewPrivileges=true`, sandboxed paths. |
| `systemd/dashboard.service` | system unit for the private web dashboard (same hardening). |
| `gateway_supervisor.py` | external supervisor daemon (runs as a **user** unit, not a cron job — see below). Detects: stale heartbeat, `deleted state.db-wal` markers, fresh "session storage could not be written" / "unable to open database file" lines in gateway logs (≥2 per 4 min). Restarts the units via `systemctl` with cooldown + hourly cap (3/h → escalates to "manual restore needed", never auto-restores state). Deduped alerts: one message per state transition (problem / recovered), not per poll cycle. |
| `systemd/supervisor.service` | user unit (`systemctl --user`) that runs `gateway_supervisor.py --supervise`. **Why user unit instead of a cron guard:** every previous guard lived inside the gateway's own cron scheduler — a circular dependency (gateway dies → cron dies → nothing resurrects the gateway). systemd resurrects the supervisor independently (`Restart=on-failure`), and linger keeps user units alive across reboots. |
| `polkit/49-mynet-hermes.rules` | lets user `hermes` run `systemctl restart/start` on the two units. Without it: `Access denied` (sudo is unusable under `NoNewPrivileges`). Install as root into `/etc/polkit-1/rules.d/`. |
| `scripts/hermes-update-run.sh` | the *only* sanctioned update flow: pause supervisor → `systemctl stop dashboard` → `hermes update --yes` → `systemctl restart gateway` + `systemctl start dashboard` → heartbeat/unit verification → ✅/❌ report. Stops the dashboard first because the update tool treats a running dashboard as "manual-serve" and would re-spawn it in a transient cron scope (the original source of double management). |

## Hard-won rules

1. **One owner per process.** The gateway was being managed by systemd *and* a self-written watchdog running `hermes gateway restart` at the same time. Result: "Gateway already running (PID …)" → systemd failed after 8 attempts, and a hung `hermes gateway restart` held `state.db`/`-wal`/`-shm` open through multiple fds, so new sessions could not write. Supervision and restarts happen **only** through `systemctl`.
2. **`hermes gateway restart` is banned from supervisors.** If the DB was swapped under live processes, Hermes halts writes and diverts messages to `sessions/*.jsonl` + `pending_messages/`; the DB itself can come out `malformed`. A robot restarting components does not fix that — it makes it worse. The supervisor escalates instead.
3. **An "up" unit can still be dead.** `systemctl is-active` is not enough: the failure signature was in log tails ("session storage could not be written") while the process ran fine. Watch heartbeats and fresh write-failure markers, not just process state.
4. **Watch the watcher without cron.** Any supervisor whose resurrection depends on the gateway's own scheduler is fiction. systemd user unit + linger is the durable answer.
5. **Alert on transitions, not on cycles.** A watcher that posts every poll turns a 2-hour outage into ~200 messages (observed). One "down" alert + one "recovered" alert per incident, with a 30-min reminder cap.
6. **Pause file.** `touch <state>/gateway_watchdog.paused` before manual maintenance (updates, restores). A stale pause (older than ~3 min, no update running) is cleared by the supervisor with an alert.
7. **Escalation, never auto-restore.** Past the per-hour restart cap the supervisor stops and asks a human to restore the DB from backup — a robot must not roll state back on its own.

## Failure classes detected

- Heartbeat stale (>5 min) — process dead or hung.
- `deleted state.db-wal` in logs — DB file swapped under a live process.
- Fresh write-refusal lines in the last minutes — session storage broken while process looks healthy.

## Environment

`gateway_supervisor.py` reads `OPS_CHAT_ID` / `OPS_THREAD_ID` for alerts (set in the unit's `Environment` or the gateway `.env`). Tokens are read from the environment at runtime — nothing is hardcoded.
