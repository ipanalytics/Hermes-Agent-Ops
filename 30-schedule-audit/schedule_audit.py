#!/usr/bin/env python3
"""Schedule audit: what can be moved to night hours and what costs significantly.

Based on "Substrate-Portable Execution" (arXiv 2609.06128): separate what a job does from when it runs; batch and off-peak windows give direct discounts, 
while daytime prime time offers nothing in return.
Plus - complexity-based routing idea (NeoHorse, arXiv 2609.08183): heavy and 
unfamiliar tasks should not run at the same time as morning tasks.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import time
from collections import defaultdict
from pathlib import Path

HOME = Path(os.environ.get("AGENT_HOME", os.environ.get("HOME", "~")))
JOBS = HOME / ".hermes/cron/jobs.json"
AUDIT = HOME / ".hermes/cron/usage_audit.jsonl"
ROLLBACK = HOME / ".hermes/data/schedule_rollback.json"
BACKUPS = HOME / ".hermes/data/cron_backups"

# "untouchable": these run at specific times (morning/day according to timezone)
TIME_CRITICAL = r"morning|daytime|evening|noon|prime|critical"
# "can be at night": weekly/monthly reviews, translations, audits, research
FLEXIBLE = r"audit|research|study|direction|translation|skill|hygiene|expense|meta|backlog|snapshot|harvest|compression-check"
NIGHT_HINT = "0-5"  # UTC hours, quiet and cost-effective


def main() -> int:
    apply = "--apply" in sys.argv
    jobs_path = Path(os.environ.get("JOBS_PATH", JOBS))
    audit_path = Path(os.environ.get("AUDIT_PATH", AUDIT))
    
    if not jobs_path.exists():
        print(f"Jobs file not found: {jobs_path}")
        return 1
        
    if not audit_path.exists():
        print(f"Audit file not found: {audit_path}")
        return 1

    jobs = json.loads(jobs_path.read_text(encoding="utf-8"))
    jobs = jobs if isinstance(jobs, list) else jobs.get("jobs", [])
    by_id = {j["id"]: j for j in jobs}

    per_job = defaultdict(lambda: {"runs": 0, "tokens": 0})
    for line in audit_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue
        e = per_job[d["job_id"]]
        e["runs"] += 1
        e["tokens"] += (d.get("prompt_tokens") or 0) + (d.get("completion_tokens") or 0)

    import re

    def expr(j: dict) -> str:
        s = j.get("schedule")
        if isinstance(s, dict):
            return str(s.get("expr") or s.get("expression") or s)
        return str(s or "")

    heavy, movable = [], []
    for jid, e in per_job.items():
        j = by_id.get(jid)
        if not j or j.get("no_agent"):
            continue
        name = j.get("name", "?")
        avg = e["tokens"] // max(e["runs"], 1)
        sched = expr(j)
        if avg >= 200_000:
            heavy.append((avg, name, sched, e["runs"]))
        if (avg >= 100_000 and re.search(FLEXIBLE, name.lower())
                and not re.search(TIME_CRITICAL, name.lower())
                and not sched.startswith(("0 1", "0 3", "0 5", "0 12", "0 13", "15 3"))):
            movable.append((avg, name, jid, sched))

    if heavy:
        print("Heavy crons (average input per run):")
        for avg, name, sched, runs in sorted(heavy, reverse=True)[:8]:
            print(f"  {name[:28]:28s} {avg/1000:7.0f} k tokens  schedule {sched:12s} runs {runs}")

    if not movable:
        print("Nothing to move: flexible heavy tasks are already scheduled during night hours")
        return 0

    print("\nCan be moved to night (not time-critical, heavy):")
    for avg, name, jid, sched in sorted(movable, reverse=True):
        print(f"  {name[:28]:28s} {avg/1000:7.0f} k  currently: {sched}")

    if apply:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        BACKUPS.mkdir(parents=True, exist_ok=True)
        backup_path = BACKUPS / f"jobs.json.bak-sched-{stamp}"
        shutil.copy2(jobs_path, backup_path)
        rollback = {}
        for avg, name, jid, sched in movable:
            rollback[jid] = {"name": name, "was": sched, "now": "0 4 * * 6"}
            for j in jobs:
                if j["id"] == jid:
                    j["schedule"] = "0 4 * * 6"  # Saturday 04:00 UTC, off-peak window
        jobs_path.write_text(json.dumps(jobs, ensure_ascii=False, indent=1), encoding="utf-8")
        ROLLBACK.write_text(json.dumps(rollback, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\nMoved: {len(rollback)} (backup {backup_path})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())