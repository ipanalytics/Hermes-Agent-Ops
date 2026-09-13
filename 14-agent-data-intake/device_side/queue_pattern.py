#!/usr/bin/env python3
"""queue_pattern.py — the device-side contract for reliable delivery.

Never trust the network with a reading:
  1. write every reading to a spool file first;
  2. POST it;
  3. rename to *.delivered ONLY on HTTP success;
  4. on failure keep retrying every cycle, indefinitely.

The spool is the source of truth. The receiver may be down for 12 hours —
the reading survives and lands when the receiver returns. Stdlib only.
"""
import json, time, urllib.request
from pathlib import Path

WEBHOOK_URL = "https://intake.example:8899/webhook"   # set me
TOKEN = "..."                                          # from the intake token file
SPOOL = Path("spool")
RETRY_EVERY_S = 30

KNOWN_SOURCES = {  # whatever your device emits
    "device": {"metric": "heart_rate", "value": 72, "timestamp": "ISO-8601"},
}


def spool(rec: dict) -> Path:
    SPOOL.mkdir(exist_ok=True)
    path = SPOOL / f"rec{time.strftime('%Y%m%dT%H%M%S%f')}Z.json"
    path.write_text(json.dumps(rec, ensure_ascii=False))
    return path


def post(rec: dict) -> bool:
    payload = {"source": rec.get("source", "device"), "metrics": [rec]}
    req = urllib.request.Request(
        WEBHOOK_URL, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "X-Health-Token": TOKEN})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            ok = r.status == 200
            print(f"-> webhook {'OK' if ok else r.status}: {r.read()[:80]}", flush=True)
            return ok
    except Exception as e:
        print(f"-> webhook FAIL: {e}", flush=True)
        return False


def deliver(rec: dict) -> None:
    path = spool(rec)
    while not post(rec):            # retry forever — network is not the source of truth
        time.sleep(RETRY_EVERY_S)
    path.rename(path.with_name(path.name + ".delivered"))


def flush_pending() -> None:
    """Re-attempt anything spooled by a previous process run."""
    for path in sorted(SPOOL.glob("*.json")):
        try:
            rec = json.loads(path.read_text())
        except Exception:
            continue
        if post(rec):
            path.rename(path.with_name(path.name + ".delivered"))


if __name__ == "__main__":
    flush_pending()
    # ...your BLE/relay loop calls deliver(rec) for each new reading
