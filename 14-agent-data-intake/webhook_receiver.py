#!/usr/bin/env python3
"""webhook_receiver.py — minimal single-file HTTPS intake receiver.

ThreadingHTTPServer + shared-token check + SQLite append. Stdlib only.
The lesson encoded here: single-threaded servers wedge on one stalled client
and stop responding (including their own ping); threading is not optional.

Run as a systemd USER unit (see systemd/webhook.service), with linger enabled,
so the receiver survives reboots and never depends on the agent gateway.

Endpoints:
  POST /webhook   -> store JSON readings
  GET  /ping      -> health check (the watchdog HTTP-pings this, not ports)
  GET  /last      -> last rows (debugging)
"""
import json, os, sqlite3, time
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

DB_FILE = os.path.expanduser("~/.local/state/intake/metrics.db")
TOKEN_FILE = os.path.expanduser("~/.local/state/intake/token.txt")
PORT = int(os.environ.get("INTAKE_PORT", "8443"))

# Token: create once, then only read. Never let a config file override it.
if not os.path.exists(TOKEN_FILE):
    os.makedirs(os.path.dirname(TOKEN_FILE), exist_ok=True)
    with open(TOKEN_FILE, "w") as f:
        f.write(os.urandom(24).hex())
    os.chmod(TOKEN_FILE, 0o600)
TOKEN = open(TOKEN_FILE).read().strip()

KNOWN = {"heart_rate": "bpm", "blood_pressure": "mmHg", "weight": "kg",
         "spo2": "%", "temperature": "°C"}


def db():
    c = sqlite3.connect(DB_FILE)
    c.execute("""CREATE TABLE IF NOT EXISTS metrics(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL, metric TEXT NOT NULL, value REAL,
        unit TEXT, systolic REAL, diastolic REAL, source TEXT, received_at TEXT)""")
    return c


def normalize(records, source):
    rows = []
    for r in records:
        metric = (r.get("metric") or r.get("type") or "").strip().lower()
        if metric not in KNOWN:
            continue
        ts = r.get("timestamp") or time.strftime("%Y-%m-%dT%H:%M:%S")
        row = {"ts": ts, "metric": metric, "unit": KNOWN[metric],
               "source": source, "systolic": None, "diastolic": None,
               "received_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
        if metric == "blood_pressure":
            row["systolic"] = float(r.get("systolic") or 0)
            row["diastolic"] = float(r.get("diastolic") or 0)
            row["value"] = row["systolic"]
        else:
            row["value"] = float(r.get("value") or r.get("qty") or 0)
        rows.append(row)
    return rows


class Handler(BaseHTTPRequestHandler):
    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/ping"):
            return self._json(200, {"status": "ok"})
        if self.path.startswith("/last"):
            c = db()
            rows = c.execute(
                "SELECT ts, metric, value, systolic, diastolic, source, received_at"
                " FROM metrics ORDER BY id DESC LIMIT 5").fetchall()
            c.close()
            return self._json(200, {"rows": rows})
        return self._json(404, {"error": "not found"})

    def do_POST(self):
        if not self.path.startswith("/webhook"):
            return self._json(404, {"error": "not found"})
        # token in any of: X-Health-Token, Authorization: Bearer, ?token=
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0) or 0))
        hdr = self.headers.get("X-Health-Token") or ""
        auth = self.headers.get("Authorization", "")
        if auth.lower().startswith("bearer "):
            hdr = hdr or auth[7:]
        ok = hdr == TOKEN or (self.path.split("token=")[-1] if "token=" in self.path else "") == TOKEN
        if not ok:
            return self._json(403, {"error": "bad token"})
        try:
            payload = json.loads(raw or b"{}")
        except Exception as e:
            return self._json(400, {"error": f"bad json: {e}"})
        records = payload.get("metrics") if isinstance(payload.get("metrics"), list) else (
            payload if isinstance(payload, list) else [payload])
        rows = normalize(records, payload.get("source") or payload.get("app") or "unknown")
        if not rows:
            return self._json(200, {"status": "ok", "stored": 0})
        c = db()
        c.executemany(
            "INSERT INTO metrics(ts,metric,value,unit,systolic,diastolic,source,received_at)"
            " VALUES(:ts,:metric,:value,:unit,:systolic,:diastolic,:source,:received_at)", rows)
        c.commit()
        c.close()
        return self._json(200, {"status": "ok", "stored": len(rows)})

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    httpd = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"intake webhook up on :{PORT}", flush=True)
    httpd.serve_forever()
