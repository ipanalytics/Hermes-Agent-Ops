# 02 — agent-gateway-supervisor

_Russian version: [README.ru.md](README.ru.md)_

**Gateway supervision done properly: systemd owns the processes, one external supervisor detects "alive but
dead" states, and a polkit grant lets the unprivileged agent restart its own units. No `gateway restart`
from inside the agent, ever.**

My agent talks to me through a **gateway** — the program that receives and sends its messages. When the
gateway dies silently, the agent looks alive but answers no one. This folder is my supervision layer for
that gateway and its private web dashboard: hardened **systemd** units (Linux's standard process manager,
the service that owns daemons), one external supervisor daemon, and a single sanctioned update script.

For a reader new to this corner of the stack: an **LLM** (*Large Language Model*) is the AI I pay to
respond to text, billed per **token** (roughly a word or fragment of a word) for each chat — a
**session** is one continuous conversation. A **scheduled job** (or **cron job**) is a task that fires
on a timer without me being there. **Hermes** is the name I gave my home AI agent: it lives on my
server, runs around the clock, and takes care of its own routine — digests, price watching, health
tracking, monitoring its own failures. The gateway is the single program through which every chat,
every scheduled job and every internal command has to pass; if it is gone, *nothing* reaches me.

The folder exists because supervising that gateway the obvious way — write a watchdog that calls
`hermes gateway restart` whenever something looks wrong — destroyed my state database and silenced
the whole agent for ~12 hours. Everything in here is the rebuilt version, plus the operational rules
that prevent the same mistake from coming back. Revision 2026-09-07.

## Why it exists

The failure I rebuilt this around happened in early September 2026. Two things were true at the same
time, and neither knew the other existed:

1. The gateway was managed by **systemd** through a unit (`gateway.service`) with
   `Restart=on-failure` and a 10-second back-off.
2. A self-written watchdog was *also* trying to manage it, by calling `hermes gateway restart` from
   a cron job that lived **inside the gateway's own scheduler**.

When the watchdog decided the gateway was misbehaving, both managers fought for it. systemd logged
`"Gateway already running (PID …)"`, retried up to its `StartLimitBurst=5` cap, and fell into
`failed`. The watchdog's `hermes gateway restart` call hung on the SQLite database, holding
`state.db`, `state.db-wal` and `state.db-shm` open through several file descriptors for hours. New
sessions could not write; messages diverted to `sessions/*.jsonl` and
`pending_messages/pending-*.json`; the active DB came out `malformed` once the contention cleared.

The whole agent was silent in every chat for ~12 hours. A health reading from one of my devices
queued locally at 05:08 and only delivered at 15:15 — zero data loss, 12 hours of latency. A
separate receiver (kept alive only by a cron watchdog *inside* the gateway) stayed dead in the same
window because its lifeline was gone with the gateway itself.

A separate class of "alive but dead" failure came up in the same period. The gateway's process was
fine, the heartbeat file was fresh, the bot simply stopped answering. The cause was different: a
log line — `FATAL: a live process holds a deleted state.db-wal or state.db-shm inode ... Refusing
to open or write so a second WAL cannot be minted` — told me that the database had been swapped
under live processes, and the gateway had correctly refused to write into the now-corrupted
sidecars. `systemctl is-active` said `active`. The gateway was useless.

Two lessons from those hours, both encoded in this folder:

- **One owner per process.** A watchdog and a process manager fighting over one service is worse
  than no supervision at all.
- **"Up" is not "healthy".** `systemctl is-active` is necessary, not sufficient. I have to watch
  the heartbeat, the fatal markers in the log tail, and the fresh write-refusal lines, and only
  act when one of those says the unit is in trouble.

## How it works

The design has five moving parts, and each one has exactly one job:

- **systemd owns the processes.** Two system units, `gateway.service` and `dashboard.service`, run
  the gateway and the private web dashboard as the unprivileged user `hermes`. Both are hardened
  with `NoNewPrivileges=true`, `PrivateTmp=true`, `ProtectSystem=strict`, `ProtectHome=read-only`,
  a tight `ReadWritePaths=` list, `ProtectKernelTunables=true`, `ProtectKernelModules=true`,
  `ProtectControlGroups=true`, `RestrictSUIDSGID=true` and `LockPersonality=true`. Both have
  `Restart=on-failure`, `RestartSec=10s`, `StartLimitIntervalSec=300` and `StartLimitBurst=5` —
  systemd will restart the gateway up to five times in five minutes if it exits non-zero, and
  then back off. The gateway slice is capped at `CPUQuota=300%` and `MemoryMax=6G` so a runaway
  model call cannot starve the rest of the host.
- **One external supervisor watches "alive but dead".** `gateway_supervisor.py` runs as a
  **systemd user unit** (not a cron job, not a process inside the gateway) and polls every 120 s
  (`LOOP_S`). It looks at three signals: the heartbeat file's age (>5 min stale is treated as
  dead), the recent tail of `errors.log` and `agent.log` for `deleted state.db-wal` markers
  (≥1 fresh line within `SIGNAL_FRESH_S=240` s is enough), and the same logs for write-refusal
  lines like `unable to open database file` / `session storage could not be written` /
  `Session DB creation failed` / `Session DB append_message failed` (≥2 fresh lines within 4 min
  to ignore one-off noise).
- **Restarts go through systemctl, never through the agent's CLI.** When the supervisor decides
  the gateway is sick, it tries `systemctl restart hermes-agent-gateway.service` first. The
  polkit grant below makes that work for the unprivileged `hermes` user. If polkit denies the
  request (someone installed the rules file in the wrong place, or the daemon was reloaded), the
  supervisor falls back to a no-root path: read `MainPID` from `systemctl show`, send `SIGTERM`,
  wait `TERM_GRACE_S=60` s, send `SIGKILL`. systemd's `Restart=on-failure` then raises a fresh
  process because `SIGKILL` produces a non-zero exit. Either way the gateway comes back under the
  same unit, owned by the same owner.
- **A hard cap turns into an escalation.** The supervisor keeps an hourly counter in
  `~/.hermes/state/gateway_watchdog.json`. After `MAX_PER_HOUR=3` restarts in a sliding 60-minute
  window it stops restarting and posts an alert: *"gateway will not come back; state.db is
  probably corrupt — restore from backup and run `systemctl restart hermes-agent-gateway.service`
  manually as root."* A robot must never roll state back on its own.
- **Alerts are de-duplicated by state transition, not by poll cycle.** A watcher that posts every
  poll turned the 2-hour incident into ~200 messages. This one posts one "down" alert when the
  problem is detected, one "recovered" alert when the heartbeat comes back, and nothing in
  between.

A **cooldown** of `COOLDOWN_S=600` s sits between consecutive restarts so a flapping gateway is
not hammered. A **pause file** at `~/.hermes/state/gateway_watchdog.paused` is honoured: while it
exists and `pgrep -f 'hermes update --yes'` returns 0 (an update is in progress), the supervisor
does nothing. If the pause file is older than 180 s and no update is running, the supervisor
deletes it and posts an alert — *"the watchdog pause from the previous update is stale; the
supervisor is active again."* That is the safety net for the case where the update crashed and
left a forever-paused watchdog behind.

The dashboard is treated separately: the supervisor does **not** try to restart it ad-hoc. The
unit has `Restart=on-failure`, so systemd brings it back on its own. The supervisor only steps in
if the dashboard unit has been inactive for `DASH_INACTIVE_ALERT_S=240` s — then it tries
`systemctl start` once and alerts in topic 30 («Система») if that fails, so I know a human with
root is required.

## Files

| Path | What it is |
|---|---|
| `systemd/gateway.service` | system unit for the messaging gateway. `Restart=on-failure`, `RestartSec=10s`, `StartLimitIntervalSec=300/StartLimitBurst=5`, `NoNewPrivileges=true`, sandboxed paths, `CPUQuota=300%`, `MemoryMax=6G`, slice `hermes-agent.slice`. Installed as root with `systemctl link` or copied into `/etc/systemd/system/`. |
| `systemd/dashboard.service` | system unit for the private web dashboard on `127.0.0.1:9119` (the same hardening, no quota because the dashboard is small). |
| `gateway_supervisor.py` | external supervisor daemon. Runs as a **user** unit (`systemctl --user`), not a cron job — see "Why user unit instead of cron" below. Detects stale heartbeat, `deleted state.db-wal` markers, fresh write-refusal lines. Restarts units through `systemctl` (with the SIGTERM/SIGKILL fallback), capped at 3 restarts per hour, with a 10-minute cooldown between attempts. Dedupes alerts: one message per state transition, not per poll. Reads `OPS_CHAT_ID` / `OPS_THREAD_ID` from the environment for Telegram alerts. |
| `systemd/supervisor.service` | user unit (`systemctl --user`) that runs `gateway_supervisor.py --supervise`. Its stdout/stderr append to `~/.hermes/logs/gateway_watchdog_supervisor.log`. **`Restart=on-failure` + `RestartSec=15s`** means systemd resurrects the supervisor itself if the Python interpreter ever dies. |
| `polkit/49-hermes-agent.rules` | polkit rule that lets the unprivileged user `hermes` run `systemctl restart/start` on `hermes-agent-gateway.service` and `hermes-agent-dashboard.service`. Without it: `Access denied` — sudo is unusable under `NoNewPrivileges=true`. Install as root into `/etc/polkit-1/rules.d/` (file name in the rules directory is `49-hermes-hermes.rules`, chown `root:root`, chmod `600`). |
| `scripts/hermes-update-run.sh` | the *only* sanctioned update flow. Pause supervisor → `systemctl stop dashboard` → `hermes update --yes` → `systemctl restart gateway` + `systemctl start dashboard` → heartbeat/unit verification → ✅/❌ report in topic 30. The dashboard is stopped first because the update tool treats a running dashboard as "manual-serve" and would re-spawn it in a transient cron scope — the original source of double management. First call goes into a detached background immediately (`setsid nohup`); the script survives a gateway restart. |

### Why user unit instead of cron for the supervisor

Every previous version of the watchdog lived inside the gateway's own cron scheduler — that is the
short version of the original 12-hour outage. The gateway dies → its cron dies → the watchdog
cannot run → nothing resurrects the gateway. A **systemd user unit** breaks the cycle: systemd
owns the supervisor's lifecycle, not the gateway. `Restart=on-failure` means a Python crash
re-spawns the supervisor immediately. `loginctl enable-linger hermes` keeps user units alive
across logouts and reboots, so the supervisor is back before I am.

## Operational rules

These are the rules I follow on the live host. They are not suggestions; they are the conditions
under which the supervisor above is correct.

1. **One owner per process.** The gateway and the dashboard are managed **only** through systemd.
   No `hermes gateway restart`, no `hermes dashboard --start` from inside an agent session, no
   ad-hoc shell backgrounding of either. Two managers racing on one service is the failure mode
   this folder was written to end.
2. **`hermes gateway restart` is banned from supervisors and update flows.** If the database was
   swapped under live processes, the gateway correctly halts writes and diverts messages to
   `sessions/*.jsonl` and `pending_messages/`. The DB itself comes out `malformed`. A robot
   restarting components does not fix it; it keeps the file locked and makes the corruption
   permanent. The supervisor's response is to escalate, not to retry.
3. **`systemctl is-active` is necessary, not sufficient.** The `alive but dead` failure had
   `is-active` returning `active` and the heartbeat fresh. The signature was in the log tail
   (`session storage could not be written`). I watch heartbeats, fresh write-refusal markers, and
   `deleted state.db-wal` FATALs — not only process state.
4. **The watchdog runs outside the thing it watches.** A supervisor whose resurrection depends
   on the service it is supposed to bring back is fiction. The supervisor is a systemd user unit
   with `Restart=on-failure` and `loginctl enable-linger hermes`. That is the durable answer.
5. **Alerts on state transitions, not on poll cycles.** One "down" message + one "recovered"
   message per incident, with a 30-minute reminder cap. The previous design turned a 2-hour
   outage into ~200 messages; that is what I am preventing here.
6. **Pause file before manual maintenance.** `touch ~/.hermes/state/gateway_watchdog.paused`
   before an update, a restore, or any other manual work. The supervisor clears it automatically
   after 180 s if the update is not running, and alerts that it did so.
7. **Escalation, never auto-restore.** Past the 3/hour cap the supervisor stops and asks a human
   to restore the state DB from backup. A robot must not roll state back on its own. The
   reasoning is simple: an automatic rollback that picks the wrong backup turns one bad hour
   into a permanent loss of everything written since.
8. **The dashboard is brought up by systemd, not by the supervisor.** The previous design's
   ad-hoc dashboard launch (via `hermes-dashboard-start.sh`) was what introduced the transient
   `hermes-worker-cron-*.scope` processes that hid the real picture from `systemctl`. The
   supervisor only verifies that the unit is `active`; if it has been inactive for 240 s, it
   tries one `systemctl start` and alerts on failure.

## Failure classes detected

The supervisor responds to three concrete failure classes. Anything else is treated as "the
gateway is healthy, do not touch".

- **Stale heartbeat.** The gateway writes `~/.hermes/state/gateway.heartbeat` on a fixed cadence.
  If `mtime` is older than `HB_STALE_S=300` s (5 minutes) the process is treated as dead or
  hung — even if `systemctl is-active` says `active`. The cause is usually a blocking call inside
  a third-party library or a model provider that never returns.
- **`deleted state.db-wal` in logs.** A `FATAL` log line with that exact substring, in the last
  240 s, in either `~/.hermes/logs/errors.log` or `~/.hermes/logs/agent.log`. The signal fires
  on a single fresh line because the message itself is the failure indicator. The supervisor
  treats it as the gateway being unable to write, restarts the unit, and hopes the DB swap was
  transient. If the next 60 minutes bring three of these, the supervisor stops restarting and
  escalates.
- **Fresh write-refusal lines in the last minutes.** At least `SIGNAL_MIN_LINES=2` lines in the
  last 240 s matching `unable to open database file` / `session storage could not be written` /
  `Session DB creation failed` / `Session DB append_message failed`. The threshold of two is
  there to ignore a single transient I/O error; two in four minutes is the gateway's own
  storage layer telling me it cannot serve sessions.

The supervisor never inspects the database directly. It only reads the log tails and the
heartbeat file. That keeps it cheap (no SQLite contention with the gateway) and keeps it
honest (it can only react to what the gateway itself has reported).

## Environment and configuration

`gateway_supervisor.py` reads its knobs from constants at the top of the file. The two that
matter operationally are `MAX_PER_HOUR=3` and `COOLDOWN_S=600` — the third restart inside an hour
turns into an escalation, and two restarts inside ten minutes turn into a wait. Bumping either is
the wrong fix for a recurring failure; the right fix is a restore from backup and a forensic look
at what made the gateway unhappy in the first place.

The supervisor reads `OPS_CHAT_ID` and `OPS_THREAD_ID` from the environment for Telegram alerts
(set in the unit's `Environment=` lines or in the gateway's `.env`). The Telegram bot token is
read at runtime from `~/.hermes/.env` — never hardcoded, never committed. State lives in
`~/.hermes/state/gateway_watchdog.json` (hourly counter and last-restart timestamp),
`~/.hermes/state/gateway_watchdog_supervisor.pid` (the supervisor's own PID, so a duplicate
launch is detected and exits cleanly), and `~/.hermes/state/gateway_watchdog.paused` (the pause
flag honoured during updates).

## Related modules

- **01-agent-wallet-guard** — the spend watchdog. The supervisor and the wallet guard share the
  same operational rule: silence is success. When the supervisor alerts, something has actually
  changed; when it does not, the gateway is healthy.
- **03-agent-ops-playbook/incidents/auto-update-restart-chain.md** — the 12-hour outage this
  folder was rebuilt after. The incident write-up includes the exact evidence (`94 × unable to
  open database file` in one day, the `Gateway already running (PID …)` log line, the transient
  cron scopes invisible to `systemctl`) that made me converge on the design in this folder.
- **03-agent-ops-playbook/incidents/gateway-alive-but-dead.md** — the second incident, the
  one that introduced the `deleted state.db-wal` check. Same playbook, same `alive but dead`
  pattern, different root cause (database swap instead of double management).
- **05-cron-of-crons** — the cron schedule that runs the gateway supervisor's *companion*
  checks (DB integrity, log rotation). The supervisor itself is a systemd unit; only auxiliary
  health checks run on cron.
- **06-hermes-plugins-skills** — the watchdog recipes in this folder are packaged as a
  reusable skill (`hermes-gateway-supervisor`), so the same supervisor can be dropped into any
  Hermes-style deployment without re-deriving the constants.
- **15-agent-token-economy** — the rationale for the `CPUQuota=300%` and `MemoryMax=6G` caps in
  the gateway unit: the supervisor protects the host, but the unit's slice protects the host
  from a single runaway model call.