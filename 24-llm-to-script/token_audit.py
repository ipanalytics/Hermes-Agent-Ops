#!/usr/bin/env python3
"""Find the next job worth converting from "model does everything" to "script collects, model writes".

Reads a usage ledger, ranks jobs by total tokens, and scores each one on two signals: how large its
average input is (a model re-reading the world every run) and how many instruction-heavy markers its
prompt contains (fetch, if it fails, then, otherwise, parse). High on both is the shortlist.

    token_audit.py --jobs jobs.json --audit usage_audit.jsonl --top 10
"""
from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path

INSTRUCTION_MARKERS = [
    r"\bfetch\b", r"\bdownload\b", r"\bparse\b", r"\bscrape\b", r"\bsearch\b",
    r"если не", r"если ошибка", r"иначе", r"затем", r"проверь, что",
    r"\bif\b.*\bfail", r"\botherwise\b", r"\bthen\b", r"\bverify\b",
]


def instruction_score(prompt: str) -> int:
    import re
    return sum(1 for m in INSTRUCTION_MARKERS if re.search(m, prompt, re.I))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", required=True)
    ap.add_argument("--audit", required=True)
    ap.add_argument("--top", type=int, default=10)
    args = ap.parse_args()

    jobs = json.loads(Path(args.jobs).read_text(encoding="utf-8"))
    jobs = jobs if isinstance(jobs, list) else jobs.get("jobs", [])
    by_id = {j["id"]: j for j in jobs}

    totals: dict[str, int] = defaultdict(int)
    inputs: dict[str, list[int]] = defaultdict(list)
    runs: dict[str, int] = defaultdict(int)
    for line in Path(args.audit).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        jid = rec.get("job_id", "?")
        tokens = rec.get("total_tokens") or (rec.get("prompt_tokens", 0) + rec.get("completion_tokens", 0))
        totals[jid] += tokens
        inputs[jid].append(rec.get("prompt_tokens") or 0)
        runs[jid] += 1

    rows = []
    for jid, total in totals.items():
        job = by_id.get(jid, {})
        avg_in = int(statistics.median(inputs[jid])) if inputs[jid] else 0
        score = instruction_score(job.get("prompt") or "")
        shortlist = avg_in >= 50000 and score >= 2
        rows.append((total, jid, job.get("name", jid), runs[jid], avg_in, score, shortlist))

    print(f"{'tokens':>12s}  {'runs':>5s}  {'median input':>12s}  {'markers':>7s}  job")
    for total, jid, name, r, avg_in, score, shortlist in sorted(rows, reverse=True)[: args.top]:
        flag = "  ← кандидат на скрипт" if shortlist else ""
        print(f"{total:12,d}  {r:5d}  {avg_in:12,d}  {score:7d}  {name[:34]}{flag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
