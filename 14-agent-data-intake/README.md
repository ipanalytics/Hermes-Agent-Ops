# 14 — agent-data-intake

_Русская версия: [README.ru.md](README.ru.md)_

**Reliable device-to-agent data intake: BLE devices, phone relays, and any webhook-posting source. The receiver is a systemd user unit (not a gateway cron), it is multi-threaded so one stuck client cannot kill it, and the device side never trusts the network — it spools and retries until delivered.**

Revision 2026-09-07, after an incident where the intake receiver died overnight and a morning health reading arrived **12 hours late — but not lost**: the device-side queue held it and flushed when the receiver came back.

## The failure class this module treats

A device (BLE cuff, phone app, IoT sensor) posts readings to a webhook receiver. The receiver is a small always-on process. Three things kill it silently:

1. **The receiver depends on the agent gateway's cron to stay alive.** Gateway dies → cron dies → nothing restarts the receiver → every reading from that moment fails. A cron-based watchdog is *not* a lifeline for anything that must outlive the gateway.
2. **The receiver is single-threaded.** One client that connects and stalls (flaky mobile link, slow body) blocks every later request — including the health-check ping — so the watchdog sees "down" and kills a process that was merely stuck behind a client.
3. **The device trusts the network.** If the POST fails, the reading is gone — the user measured at 05:08, the receiver was down until 15:15, and the morning number simply never arrives.

## Files

| Path | What it is |
|---|---|
| `systemd/webhook.service` | user unit (`systemctl --user`) for the HTTP receiver. `Restart=on-failure`, `RestartSec=5s`, logs to a persistent path. Linger keeps user units alive across reboots. |
| `systemd/tls-proxy.service` | user unit for a small threaded TLS proxy in front of the receiver when the endpoint is public (`:8899 TLS → :8443 HTTP`). Same restart policy. Certificates come from a **persistent** directory, never `/tmp`. |
| `webhook_receiver.py` | minimal single-file receiver: `ThreadingHTTPServer`, shared-token check (header/query), SQLite append. ~100 lines, stdlib only. |
| `device_side/queue_pattern.py` | the device-side contract in code: write every reading to a spool file first, then POST; on failure keep retrying every cycle; rename to `*.delivered` only after HTTP success. Data survives receiver outages of any length. |

## Operational rules

1. **The receiver is infrastructure, not an agent feature.** Give it its own unit and its own restart policy. If it lives inside the gateway's world, a gateway incident becomes a data-intake incident too (observed: one outage chain took down both, and the morning reading queued for 12 h).
2. **One stuck client must not be able to kill the server.** Single-threaded stdlib servers wedge on a stalled connection — the whole process stops responding, including its own ping endpoint. Use `ThreadingHTTPServer` (or an async server). The "alive but dead" failure exists for intake servers too, not just gateways.
3. **Logs and certs do not belong in `/tmp`.** `/tmp` is wiped on reboot; a receiver whose TLS cert lives there dies at the worst possible moment (the morning measurement). Persistent paths only.
4. **Never lose a reading to the network.** The device side writes locally first (`spool/*.json`), POSTs, and only marks the file delivered on HTTP success. On failure it retries every cycle — indefinitely. The queue is the source of truth, not the network.
5. **Scan continuously, not on a schedule.** A BLE watcher that scans "5:10–5:20" misses the user who measures at 5:08. An always-on scan loop (12 s scan, 5 s gap ≈ 17 s cycle) catches any advertisement burst longer than the cycle — 6/6 live catches in production. Never ask the user to fit a window.
6. **Health check = real request, not port check.** `ss -tln` shows ports "listening" on a wedged process. The watchdog must HTTP-PING the receiver (`GET /ping`, expect 200 within a few seconds).
7. **Verify end-to-end without the device.** POST a synthetic reading with the real token through the TLS proxy and confirm the row lands in SQLite; then delete it. Proves receiver → DB before you debug BLE.
8. **Alert on transitions.** The VM/device-side watchdog that checks the receiver every 5 minutes must alert once per incident (state file), with at most a 30-minute reminder — not on every poll.

## Failure timeline (observed)

```
02:00  receiver dies (stuck client / killed with an unrelated restart chain)
05:08  user measures; device BLE daemon receives the reading (24/7 scan)
05:08  POST fails (connection refused) → reading spooled, retry every ~17 s
05:08–15:15  retries fail; nothing restarts the receiver (its cron lifeline is down too)
15:15  receiver unit starts (new architecture); first retry succeeds → delivered
15:15  spool flushed, *.delivered renamed; morning reading lands in SQLite intact
```

Total loss: **zero**. Latency: 12 h, caused entirely by the missing restart policy — the fix this module ships.

## Testing without a device

```bash
# simulate a device: POST one reading through the TLS proxy
curl -sk -X POST https://intake.example:8899/health/webhook \
  -H "X-Health-Token: $(cat /path/to/token_file)" \
  -H "Content-Type: application/json" \
  -d '{"source":"test","metrics":[{"metric":"heart_rate","value":60}]}'
# → {"status":"ok","stored":1}; then DELETE the row in SQLite.
```

## Environment

Receiver reads its token from a token file at startup (never a config that may hold a stale example). Units set `HOME` explicitly — `expanduser()` inside systemd user units needs it.
