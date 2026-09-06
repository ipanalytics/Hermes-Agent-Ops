#!/bin/bash
# supervisor_guard.sh — scheduler cron (every ~5 min): resurrect the external
# supervisor if it died. The supervisor's PID dies with every gateway restart
# (it is a child of the old gateway's process tree only if spawned from there —
# when spawned detached via setsid it survives, but belt-and-braces: this guard
# is scheduler-owned and survives everything).
#
# CRITICAL: pgrep with an ANCHORED regex on the full command line. Without an
# anchor, `pgrep -f gateway_supervisor.py` also matches this very guard and
# any editor/backup process touching the file.
#
# Install in the agent's scheduler as a no-agent job every 5 minutes:
#   empty stdout = silence = nothing delivered.

SUPERVISOR="/usr/local/bin/gateway_supervisor.py"
SUPERVISE_ARGS="--supervise --state-dir /var/lib/agent/state --log-dir /var/lib/agent/logs --restart-cmd 'systemctl restart agent-gw'"
LOG="/var/log/gateway_supervisor_guard.log"

if ! pgrep -f "^python3 ${SUPERVISOR} --supervise" > /dev/null 2>&1; then
    echo "$(date '+%F %T') supervisor dead — respawning" >> "$LOG"
    setsid python3 "$SUPERVISOR" $SUPERVISE_ARGS >> "$LOG" 2>&1 < /dev/null &
    echo "supervisor was dead — respawned"
fi
