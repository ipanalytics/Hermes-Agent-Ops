#!/usr/bin/env python3
"""Cost per successful task, per role — not dollars per million tokens.

A price list answers "what does a token cost". It does not answer "what does a finished piece of
work cost", which is the number a budget is actually spent against. This tool joins a usage ledger
with a job list and a price map, maps jobs to roles by name, and reports cost per *successful* run.
Failures are paid for too, so they are counted in the numerator and excluded from the denominator.

    cost_per_outcome.py --jobs jobs.json --audit usage_audit.jsonl --prices prices.json
"""
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

CONFIG = Path(__file__).with_name("examples")


def load(path: Path) -> dict | list:
    return json.loads(path.read_text(encoding="utf-8"))


def price_for(model: str, prices: dict) -> tuple[float, float]:
    low = (model or "").lower()
    for key, val in prices.items():
        if key in low:
            return float(val[0]), float(val[1])
    return float(prices.get("_default", [0.15, 0.60])[0]), float(prices.get("_default", [0.15, 0.60])[1])


def role_for(name: str, roles: dict) -> str:
    for role, pattern in roles.items():
        if re.search(pattern, name.lower()):
            return role
    return "other"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", required=True)
    ap.add_argument("--audit", required=True)
    ap.add_argument("--prices", required=True, help="JSON: {job_name_regex_config} see examples/prices.json")
    ap.add_argument("--window-days", type=int, default=7)
    args = ap.parse_args()

    cfg = load(Path(args.prices))
    prices, roles = cfg["prices"], cfg.get("roles", {})
    names = {j["id"]: j.get("name", "?") for j in (load(Path(args.jobs)) if args.jobs else [])}

    agg: dict[str, dict] = defaultdict(lambda: {"runs": 0, "ok": 0, "cost": 0.0})
    import time
    cutoff = time.time() - args.window_days * 86400
    for line in Path(args.audit).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        try:
            epoch = time.mktime(time.strptime(rec["ts"][:19], "%Y-%m-%dT%H:%M:%S"))
        except Exception:
            continue
        if epoch < cutoff:
            continue
        pin, pout = price_for(rec.get("model"), prices)
        cost = (rec.get("prompt_tokens") or 0) / 1e6 * pin + (rec.get("completion_tokens") or 0) / 1e6 * pout
        entry = agg[role_for(names.get(rec.get("job_id"), ""), roles)]
        entry["runs"] += 1
        entry["ok"] += 0 if rec.get("error") else 1
        entry["cost"] += cost

    print(f"cost per successful task (last {args.window_days} days)")
    rows = []
    for role, e in agg.items():
        rows.append((e["cost"] / max(e["ok"], 1), role, e))
    for cpo, role, e in sorted(rows, reverse=True):
        print(f"  {role:24s} ok {e['ok']:4d}/{e['runs']:<4d}  ${e['cost']:.2f}  →  ${cpo:.3f} per success")
    total = sum(e["cost"] for _, _, e in rows)
    ok = sum(e["ok"] for _, _, e in rows)
    print(f"  {'TOTAL':24s} ok {ok:4d}         ${total:.2f}  →  ${total / max(ok, 1):.3f} per success")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
