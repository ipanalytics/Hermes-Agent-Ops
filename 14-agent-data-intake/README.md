# 14 — agent-data-intake

_Russian version: [README.ru.md](README.ru.md)_

![License](https://img.shields.io/github/license/ipanalytics/Hermes-Agent-Ops)
![Status](https://img.shields.io/badge/status-active-brightgreen)
![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue)

**A small always-on service that receives readings from devices — a BLE blood-pressure cuff, a phone app, any source that knows how to POST JSON to an HTTPS URL — and stores them in a local SQLite file. The receiver is its own systemd user unit, not a job on the gateway's scheduler (a "cron" job). It is multi-threaded, so one slow client cannot wedge the whole thing. The device side never trusts the network: every reading lands in a local spool file first, and the file is renamed to `*.delivered` only after the POST returns 200. The spool is the source of truth, not the network.**

Revision 2026-09-07. The trigger was an incident in which the receiver died overnight, and my morning reading reached me **twelve hours late — not lost**: the device-side spool held it and flushed it the moment the receiver came back.

## The problem this folder exists to solve

Hermes, my home agent, lives on a server I keep running. Some of the things it needs from the outside world come from devices I wear or carry — a Bluetooth (BLE) blood-pressure cuff that posts my numbers, a phone app that uploads a weight or a sleep score, an IoT sensor that reports something each minute. A device cannot talk to a database directly; it has to talk to *something* on the server. That something is a tiny HTTP receiver, sometimes called a webhook: the device POSTs JSON to an address, the receiver checks a shared token, and the reading is appended to a small SQLite file the rest of the agent reads.

Three things kill that receiver silently, and each one costs me a real measurement:

1. **The receiver is started by the gateway's scheduler.** The gateway is the long-running process that hosts the agent. Its scheduler runs cron-style jobs at fixed times. When the gateway is restarted for an upgrade, every unit it had spawned dies with it — and a cron-based watchdog (a tiny script that periodically checks "is the receiver alive? if not, start it") is no help, because the watchdog itself is the thing that died. A cron watchdog is not a lifeline for anything that must outlive the gateway.
2. **The receiver is single-threaded.** The simplest HTTP servers in Python's standard library process one request at a time. If one client connects and stalls — a flaky mobile link, a slow body upload — every later request blocks behind it, including the very ping the watchdog relies on. The watchdog sees "no answer", concludes the receiver is broken, and kills a process that was merely stuck behind one client. The "alive but dead" failure exists for intake servers too, not only for gateways.
3. **The device trusts the network.** If the device POSTs and gets nothing back, it forgets the reading. I measured at 05:08, the receiver stayed down until 15:15, and the morning number simply never arrived. The fix is not a faster network: it is a queue the device owns.

This folder ships the four pieces that fix all three: a systemd user unit with its own restart policy, a threaded receiver (~100 lines of stdlib), a small threaded TLS proxy for a public endpoint, and the queue-pattern contract every device-side sender should ship.

## Files

| Path | What it is |
|---|---|
| `systemd/webhook.service` | A user unit (`systemctl --user`) for the HTTP receiver. `Restart=on-failure`, `RestartSec=5s`, logs to a persistent path under `~/.local/state/intake/`. The unit is enabled with `linger` so it survives reboots and is independent of the gateway. |
| `systemd/tls-proxy.service` | A user unit for a small threaded TLS proxy in front of the receiver when the endpoint is public (`:8899 TLS → :8443 HTTP`). Same restart policy. Certificates come from a **persistent** directory, never `/tmp`. |
| `webhook_receiver.py` | A minimal single-file receiver. `ThreadingHTTPServer`, a shared-token check (header or `?token=` query), a SQLite append, and three endpoints: `POST /webhook` to store, `GET /ping` for the watchdog, `GET /last` for debugging. ~120 lines, Python standard library only. |
| `device_side/queue_pattern.py` | The device-side contract in code: write every reading to a spool file first (`spool/recYYYYMMDDTHHMMSSffffffZ.json`), then POST it; on failure, keep retrying every cycle, indefinitely; rename to `*.delivered` only after HTTP success. On startup the script also flushes anything a previous run left behind (`spool/*.json` → `*.delivered`). Stdlib only. |

A word on the database fields, because they decide what the agent can later read: `metrics(id, ts, metric, value, unit, systolic, diastolic, source, received_at)`. `ts` is when the device says the measurement happened; `received_at` is when the row landed. Both matter — they let me tell "no reading that morning" apart from "the row arrived later".

## Why I keep it the way I do

1. **The receiver is infrastructure, not an agent feature.** It runs as its own systemd user unit with its own restart policy. While it lived inside the gateway's world, one gateway outage took the intake down with it — and my morning reading queued for twelve hours before the receiver came back. The unit pattern is the same one module 02 (agent-gateway-supervisor) uses for the gateway itself: anything that must outlive the gateway needs a restart policy the gateway does not own.
2. **One stuck client must not be able to kill the server.** Single-threaded servers in the Python standard library wedge on a stalled connection: the whole process stops responding, including its own `/ping` endpoint. That is why the receiver uses `ThreadingHTTPServer` (and the TLS proxy uses a threaded socket server). The watchdog then has a real signal to act on, not a false one.
3. **Logs and certificates do not belong in `/tmp`.** `/tmp` is wiped on reboot; a receiver whose TLS certificate lives there dies at the worst possible moment — the morning measurement. The unit files write logs to `~/.local/state/intake/`, and certificates live in a persistent directory the user controls.
4. **Never lose a reading to the network.** The device side writes locally first (`spool/*.json`), POSTs, and only marks the file delivered on HTTP success. On failure it retries every cycle — indefinitely. The queue is the source of truth; the network is a delivery mechanism. The receiver may be down for twelve hours; the reading survives and lands when it returns.
5. **Scan continuously, not on a schedule.** A BLE watcher that scans "5:10–5:20" misses me measuring at 5:08. An always-on scan loop (12 s scan, 5 s gap ≈ 17 s cycle) catches any advertisement burst longer than the cycle — six out of six live catches in production. I never ask the user to fit a window.
6. **Health check = real request, not port check.** `ss -tln` shows ports "listening" on a wedged process. The watchdog HTTP-pings the receiver (`GET /ping`, expect 200 within a few seconds). That is the only signal that distinguishes "alive" from "listening".
7. **End-to-end verification without the device.** I POST a synthetic reading with the real token through the TLS proxy and confirm the row lands in SQLite; then I delete the row. That proves the receiver → DB path before BLE debugging starts — and it runs without the device being anywhere near the server.
8. **Alert on transitions, not polls.** The VM/device-side watchdog checks the receiver every five minutes, but it alerts once per incident (a state file tracks the current state), with at most a thirty-minute reminder — not on every poll. A two-hour outage produces ~2 messages, not ~24.

## What the token file looks like

The receiver generates its own token on first start and stores it at `~/.local/state/intake/token.txt` with mode `0600`. The unit file sets `HOME=/home/USER` explicitly because `os.path.expanduser("~")` inside a systemd user unit does not work without it — the unit does not have a login session, so the home directory is empty unless it is given one. The shared token can arrive in any of three places: the `X-Health-Token` header, or the standard HTTP `Authorization` header (using the token format most clients expect for HTTP token auth), or a `?token=…` query parameter on the URL. None of the three override the token file: the file is the source of truth, the request is just a way to send it.

## Failure timeline (observed)

```
02:00  receiver dies (a stalled client; killed by an unrelated restart chain)
05:08  I measure; device BLE daemon receives the reading (24/7 scan)
05:08  POST fails (connection refused) → reading spooled, retry every ~17 s
05:08–15:15  retries fail; nothing restarts the receiver (its cron lifeline is down too)
15:15  receiver unit starts under the new architecture; first retry succeeds → delivered
15:15  spool flushed, *.delivered renamed; morning reading lands in SQLite intact
```

Total loss: **zero readings**. Latency: 12 hours, caused entirely by the missing restart policy — the fix this module ships.

## Testing without a device

```bash
# simulate a device: POST one reading through the TLS proxy
curl -sk -X POST https://intake.example:8899/health/webhook \
  -H "X-Health-Token: $(cat /path/to/token_file)" \
  -H "Content-Type: application/json" \
  -d '{"source":"test","metrics":[{"metric":"heart_rate","value":60}]}'
# → {"status":"ok","stored":1}; then DELETE the row in SQLite.
```

That single round-trip covers the whole path from outside the receiver to inside the database, with the real token and the real TLS layer. If it works, BLE debugging starts from a known-good baseline; if it fails, the receiver is the problem, not the radio.

## Related

- **02-agent-gateway-supervisor** — the unit pattern that 14 reuses for the receiver: anything that must outlive the gateway needs a restart policy the gateway does not own.
- **03-agent-ops-playbook** — the incident that put the receiver on its own unit in the first place.
- **05-cron-of-crons** — the alert-noise-budget rule that keeps the watchdog from spamming me on every poll.

## License

MIT License — see the LICENSE file in the repository root.