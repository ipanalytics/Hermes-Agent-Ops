#!/usr/bin/env python3
"""Routing outcomes: which models actually handle the jobs.

Connects cron/usage_audit.jsonl (run → model, tokens, error, silence) and jobs.json
(current job status). Prints a compact report: per-model runs, tokens, error rates;
per-job cheapest and most expensive models where failures occurred.
Execution: manual or weekly no_agent cron.
"""
from __future__ import annotations

import collections
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

HOME = Path(os.environ.get("AGENT_HOME", "~"))
AUDIT = HOME / ".hermes/cron/usage_audit.jsonl"
JOBS = HOME / ".hermes/cron/jobs.json"


def get_paths():
    """Helper for tests to override file locations."""
    return AUDIT, JOBS
DAYS = int(os.environ.get("ROUTING_WINDOW_DAYS", "14"))


def load_jobs(jobs_path=None):
    path = jobs_path or JOBS
    data = json.load(open(path, encoding="utf-8"))
    jobs = data if isinstance(data, list) else data.get("jobs", [])
    return {j["id"]: j for j in jobs}


def main(audit_path=None, jobs_path=None) -> int:
    audit = audit_path or AUDIT
    cutoff = (datetime.now(timezone.utc) - timedelta(days=DAYS)).timestamp()
    jobs = load_jobs(jobs_path)
    per_model = collections.defaultdict(lambda: {"runs": 0, "tok": 0, "err": 0, "silent": 0})
    per_job = collections.defaultdict(lambda: collections.Counter())
    job_models = collections.defaultdict(collections.Counter)

    for line in open(audit, errors="replace"):
        try:
            r = json.loads(line)
        except Exception:
            continue
        try:
            ts = datetime.fromisoformat(str(r.get("ts") or "").replace("Z", "+00:00")).timestamp()
        except Exception:
            continue
        if ts < cutoff:
            continue
        m = r.get("model") or "?"
        jid = r.get("job_id") or "?"
        toks = r.get("total_tokens") or 0
        bad = 1 if r.get("error") else 0
        d = per_model[m]
        d["runs"] += 1
        d["tok"] += toks
        d["err"] += bad
        d["silent"] += 1 if r.get("response_silent") else 0
        per_job[jid][m] += toks
        job_models[jid][m] += 1

    if not per_model:
        print("Routing: no audit data in window.")
        return 0

    print(f"Routing outcomes over {DAYS} days — by model:")
    for m, d in sorted(per_model.items(), key=lambda kv: -kv[1]["tok"]):
        err_pct = d["err"] / d["runs"] * 100 if d["runs"] else 0
        print(f"  {m:34s} runs {d['runs']:4d} | {d['tok']/1e6:7.1f}M tok | errors {d['err']:2d} ({err_pct:.0f}%)")

    print("\nWhere model is most expensive (candidates for downgrade):")
    for jid, models in sorted(per_job.items(), key=lambda kv: -sum(kv[1].values()))[:6]:
        name = jobs.get(jid, {}).get("name", "(deleted)")
        m, toks = models.most_common(1)[0]
        j = jobs.get(jid, {})
        flags = []
        if j.get("no_agent"):
            flags.append("no_agent")
        print(f"  {name[:34]:34s} {toks/1e6:7.1f}M | {m} | currently: {j.get('model') or '—'}{(' [' + ','.join(flags) + ']') if flags else ''}")

    fails = [(jid, jobs.get(jid, {}).get("name", "?"), j.get("last_status"))
             for jid, j in jobs.items() if j.get("enabled") and (j.get("last_status") not in (None, "ok"))]
    if fails:
        print("\nCrons not in ok status:")
        for jid, name, st in fails:
            print(f"  {name} — {st}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
