#!/usr/bin/env python3
"""Route each scheduled job to a model tier by measured difficulty, not by habit.

Two failure modes cost money in opposite directions: a reasoning-heavy job pinned to the cheapest
model fails and retries (paying twice for a worse answer), and a mechanical job pinned to a strong
model pays ten times the price for the same output. This tool scores every job from what it actually
did — completion length, error rate, output shape — and recommends a tier, with a hard rule learned
the hard way: **a repin that increases the price per token of a mechanical job is refused.**

    difficulty_router.py --jobs jobs.json --audit usage_audit.jsonl --prices prices.json
    difficulty_router.py ... --apply      # repin + write a rollback file
"""
from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import time
from collections import defaultdict
from pathlib import Path

TEMPLATE_MARKERS = [r"^\s*\d+[).]\s", r"---", r"```", r"\bшаг\s*\d", r"\bstep\s*\d", r"^\s*[-*]\s"]


def percentile(values: list[float], frac: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    idx = min(len(values) - 1, int(frac * len(values)))
    return values[idx]


def features(records: list[dict]) -> dict:
    comp = [r.get("completion_tokens") or 0 for r in records]
    prompts = [r.get("prompt_tokens") or 0 for r in records]
    errors = sum(1 for r in records if r.get("error"))
    return {
        "runs": len(records),
        "median_completion": statistics.median(comp) if comp else 0,
        "p90_completion": percentile([float(c) for c in comp], 0.9),
        "median_prompt": statistics.median(prompts) if prompts else 0,
        "error_rate": errors / len(records) if records else 0.0,
    }


def verdict(feat: dict, bands: dict) -> tuple[str, str]:
    """Return (tier, reason). Tier is 'plain' | 'mid' | 'reasoning'."""
    if feat["runs"] < bands.get("min_runs", 3):
        return "mid", "мало прогонов: не классифицируем, оставляем как есть"
    if feat["p90_completion"] >= bands.get("reasoning_p90", 3000) or feat["error_rate"] >= bands.get("error_heavy", 0.2):
        return "reasoning", f"p90 ответа {feat['p90_completion']:.0f} токенов, ошибок {feat['error_rate']:.0%}"
    if feat["median_completion"] <= bands.get("plain_median", 400) and feat["error_rate"] <= bands.get("plain_error", 0.05):
        return "plain", f"медиана ответа {feat['median_completion']:.0f} токенов, ошибок {feat['error_rate']:.0%}"
    return "mid", f"середина: медиана {feat['median_completion']:.0f}, p90 {feat['p90_completion']:.0f}"


def price_of(model: str, prices: dict) -> tuple[float, float]:
    for key, val in prices.items():
        if key != "_default" and key in (model or "").lower():
            return float(val[0]), float(val[1])
    default = prices.get("_default", [0.15, 0.60])
    return float(default[0]), float(default[1])


def main() -> int:
    ap = argparse.ArgumentParser(description="Model tier routing from measured difficulty")
    ap.add_argument("--jobs", required=True)
    ap.add_argument("--audit", required=True)
    ap.add_argument("--prices", required=True, help="JSON with 'prices' and 'tiers' (model per tier)")
    ap.add_argument("--window-days", type=int, default=14)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--repin-command", default="hermes cron edit {job_id} --model {model} --provider {provider}")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    cfg = json.loads(Path(args.prices).read_text(encoding="utf-8"))
    prices, tiers = cfg["prices"], cfg["tiers"]
    bands = cfg.get("bands", {})
    jobs = json.loads(Path(args.jobs).read_text(encoding="utf-8"))
    jobs = jobs if isinstance(jobs, list) else jobs.get("jobs", [])

    cutoff = time.time() - args.window_days * 86400
    per_job: dict[str, list[dict]] = defaultdict(list)
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
        if epoch >= cutoff:
            per_job[rec.get("job_id", "?")].append(rec)

    actions, refusals, rollback = [], [], {}
    for job in jobs:
        jid = job["id"]
        recs = per_job.get(jid, [])
        feat = features(recs)
        tier, why = verdict(feat, bands)
        current = job.get("model") or ""
        target = tiers[tier]
        if not target or target["model"] == current:
            continue
        cur_in, cur_out = price_of(current, prices)
        new_in, new_out = price_of(target["model"], prices)
        dearer = new_in + new_out > cur_in + cur_out
        mechanical = tier == "plain"
        line = (f"{job.get('name', jid)[:28]:30s} {tier:9s} {why[:52]:54s} "
                f"{current or 'default'} → {target['model']}")
        if dearer and mechanical:
            refusals.append(line + "  ❌ отказ: механика не должна дорожать")
            continue
        actions.append(line)
        rollback[jid] = {"model": current, "provider": job.get("provider")}

    for line in actions:
        print(line)
    for line in refusals:
        print(line)
    if not actions:
        print("перепинов нет: маршрутизация уже соответствует измерениям")
        return 0

    if args.apply and not args.dry_run:
        for jid, previous in rollback.items():
            target = next(t for t in tiers.values() if t["model"])
            cmd = args.repin_command.format(job_id=jid, model=target["model"], provider=target.get("provider", "openrouter"))
            subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
        Path("routing_rollback.json").write_text(json.dumps(rollback, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"перепин применён: {len(rollback)}; откат — routing_rollback.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
