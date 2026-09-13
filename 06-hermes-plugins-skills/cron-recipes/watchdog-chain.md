# Cron recipe: watchdog chain (script + guard)

Goal: a long-lived service (webhook receiver, tunnel, gateway, BLE daemon)
with no root/systemd available, kept alive by the scheduler.

## Pattern

1. **Watchdog script** (`watchdog.sh`): checks the port/process/heartbeat;
   if dead — restarts detached (`setsid`), prints a line (alert); if healthy —
   prints NOTHING.
2. **Scheduler job**: `no_agent`, runs the script every 3–5 min, stdout
   delivered verbatim. Empty stdout = silence = zero noise. Non-zero exit or
   timeout = automatic error alert.
3. For the gateway itself: policy blocks gateway-restart from scheduler jobs
   (restart-loop protection) — use the EXTERNAL supervisor instead
   (`02-agent-gateway-supervisor`), and keep this watchdog only for services
   that are safe to restart.

## Rules learned in production

- **Background processes started from the agent's terminal die with the
  agent's gateway** — detach via a wrapper script that `setsid`s itself
  (self-reexec), never via a bare `&` from a tool call.
- **pgrep must be anchored**: `pgrep -f "^<full path> --flag"` — an unanchored
  pattern matches the guard itself and any editor touching the file.
- **One watchdog per service**, not one mega-script: a crash in one service
  must not silence the others.
- Watchdog restarts the service but NOT itself — the scheduler does that on
  the next tick automatically (cron re-spawns are free).

## Example skeleton

```bash
#!/bin/bash
# health_webhook_watchdog.sh — restart webhook receiver if port 8443 is dead
if ! ss -tln | grep -q ':8443 '; then
    echo "$(date '+%F %T') webhook down — restarting" 
    setsid python3 /opt/services/webhook.py >> /var/log/webhook.log 2>&1 < /dev/null &
    echo "webhook was down — restarted"
fi
# healthy -> prints nothing -> scheduler delivers nothing
```
