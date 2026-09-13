#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""digest_health.py — journal of digest delivery health.

Cron script that analyzes job execution history from an audit log file 
(~/.hermes/cron/usage_audit.jsonl) and compares actual digest runs 
over the last 7 full days with expected schedules, generating reports 
about coverage, silence periods, and errors.
"""
import json
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone

H = os.path.expanduser
AUDIT = os.environ.get("HERMES_AUDIT_LOG", H("~/.hermes/cron/usage_audit.jsonl"))
JOBS = os.environ.get("HERMES_JOBS_FILE", H("~/.hermes/cron/jobs.json"))
STATE = os.environ.get("HERMES_DIGEST_HEALTH_STATE", H("~/.hermes/data/digest_health_state.json"))

# Digests: id -> (short name, expected-function based on date).
# expected calculates how many times the cron SHOULD have executed in the window according to its schedule (UTC).
def _weekdays(dates, days):
    return sum(1 for d in dates if d.weekday() in days)

DIGESTS = [
    ("2f3123db64ce", "morning-releases", lambda dates: len(dates)),          # daily
    ("e70f41682aea", "weekday-day-releases", lambda dates: _weekdays(dates, (0, 1, 2, 3, 4))),
    ("cb6b23cfb9b0", "weekend-releases", lambda dates: _weekdays(dates, (5, 6))),
    ("8eafc8691a13", "morning-train", lambda dates: _weekdays(dates, (0, 1, 2, 3, 4))),
    ("146422f4e1bc", "ai-digest", lambda dates: len(dates)),
    ("0b97e5eb584f", "peptides-mon", lambda dates: _weekdays(dates, (0,))),
    ("abcad3a965cf", "gene-digest", lambda dates: len(dates)),
    ("3838c462f17b", "streaming-mon", lambda dates: _weekdays(dates, (0,))),
    ("f2ff7edfccd2", "expense-sat", lambda dates: _weekdays(dates, (5,))),
]

EMOJI = {0: "🔴", 1: "🟡", 2: "🟢"}


def main():
    try:
        with open(JOBS) as f:
            jobs = {j["id"]: j for j in json.load(f)["jobs"]}
    except Exception:
        jobs = {}

    now = datetime.now(timezone.utc)
    # Window: 7 full days up to today (today is still ongoing — not counted).
    start = (now - timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)
    end = now.replace(hour=0, minute=0, second=0, microsecond=0)
    window_dates = [start + timedelta(days=i) for i in range(7)]

    runs = defaultdict(list)  # job_id -> list of audit records in the window
    if os.path.exists(AUDIT):
        with open(AUDIT) as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                ts = rec.get("ts", "")
                try:
                    t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                except Exception:
                    continue
                if start <= t < end:
                    runs[rec.get("job_id")].append(rec)

    rows = []
    for jid, label, exp_fn in DIGESTS:
        recs = runs.get(jid, [])
        expected = exp_fn(window_dates)
        actual = len(recs)
        silent = sum(1 for r in recs if r.get("response_silent"))
        errors = sum(1 for r in recs if r.get("error"))
        worst_ms = max((r.get("duration_ms") or 0) for r in recs) if recs else 0
        cov = (actual / expected) if expected else 1.0
        level = 0 if (errors > 0 or cov < 0.8) else (1 if cov < 1.0 else 2)
        rows.append({
            "label": label, "jid": jid, "expected": expected, "actual": actual,
            "silent": silent, "errors": errors, "worst_ms": worst_ms,
            "cov": cov, "level": level, "alive": jid in jobs,
        })

    # Comparison with the previous week.
    prev = None
    if os.path.exists(STATE):
        try:
            with open(STATE) as f:
                prev = json.load(f)
        except Exception:
            prev = None
    
    # Check that prev is a dictionary and has the "jobs" key
    if isinstance(prev, dict) and "jobs" in prev:
        prev_cov = {k: v.get("cov", 1.0) for k, v in prev["jobs"].items()}
    else:
        prev_cov = {}

    out = []
    week = f"{start.strftime('%d.%m')}–{(end - timedelta(days=1)).strftime('%d.%m')}"
    out.append(f".recv **Deliveries for the week** ({week}, UTC)")
    worst = 0
    for r in rows:
        name = jobs.get(r["jid"], {}).get("name") or r["label"]
        cov_s = f"{r['actual']}/{r['expected']}"
        parts = [f"{EMOJI[r['level']]} {r['label']}: {cov_s}"]
        if r["silent"]:
            parts.append(f"silent {r['silent']}")
        if r["errors"]:
            parts.append(f"errors {r['errors']}")
        if r["worst_ms"] > 120000:
            parts.append(f"slow {r['worst_ms'] // 1000}s")
        line = " · ".join(parts)
        pc = prev_cov.get(r["jid"])
        if pc is not None and r["expected"] and pc > r["cov"]:
            line += " ⬇️"
        out.append(f"• {line}")
        worst = max(worst, r["level"])
    if worst >= 1:
        out.append("_There are gaps — see last_error/check, fix if repeated for 2+ days._")

    # Save state for trend tracking.
    st = {"week_start": start.isoformat(),
          "jobs": {r["jid"]: {"expected": r["expected"], "actual": r["actual"],
                              "silent": r["silent"], "errors": r["errors"],
                              "cov": round(r["cov"], 3)} for r in rows}}
    with open(STATE + ".tmp", "w") as f:
        json.dump(st, f, ensure_ascii=False, indent=1)
    os.replace(STATE + ".tmp", STATE)

    print("\n".join(out))


if __name__ == "__main__":
    main()