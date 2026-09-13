#!/usr/bin/env python3
"""Check the effect of changing context compaction policy.

Collects baseline data BEFORE the change (3 days), then compares after 3 days: daily cost,
compression ratio (to the compaction model), number of compaction calls and cache read/input ratio.
Prints verdict once. Remains silent until observation window closes (for cron usage).
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Configuration via environment variables with defaults
HOME = Path.home()
DB_PATH = os.getenv("HERMES_DB_PATH", str(HOME / ".hermes/state.db"))
STATE_FILE = os.getenv("COMPACT_STATE_FILE", str(HOME / ".hermes/data/compaction_experiment.json"))
BASELINE_DAYS = int(os.getenv("BASELINE_DAYS", "3"))
OBSERVE_DAYS = int(os.getenv("OBSERVE_DAYS", "3"))
COMPACT_MODEL_NAME = os.getenv("COMPACT_MODEL_NAME", "glm-5.3-flash")


def metrics(start: float, end: float) -> dict:
    """Calculate usage metrics between start and end timestamps."""
    db_path = Path(DB_PATH)
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")
    
    con = sqlite3.connect(db_path)
    tot_cost = tot_in = tot_cache = comp_cost = comp_calls = 0.0
    days = max((end - start) / 86400, 0.01)
    
    for model, inp, cache, cost, calls, ls in con.execute(
            "SELECT model, input_tokens, cache_read_tokens, estimated_cost_usd, api_call_count, last_seen FROM session_model_usage"):
        try:
            ts = float(ls)
        except Exception:
            continue
        if not (start <= ts <= end):
            continue
        tot_cost += float(cost or 0)
        tot_in += inp or 0
        tot_cache += cache or 0
        if model and COMPACT_MODEL_NAME in model:
            comp_cost += float(cost or 0)
            comp_calls += calls or 0
    
    con.close()
    return {
        "cost_per_day": tot_cost / days, 
        "compaction_cost_per_day": comp_cost / days,
        "compaction_calls": comp_calls, 
        "cache_ratio": (tot_cache / tot_in) if tot_in else 0,
        "cost_total": tot_cost
    }


def main() -> int:
    """Main function to run the compaction effect check."""
    # Determine the change timestamp - normally this would be set externally
    # The timestamp comes from an environment variable or a default
    change_timestamp_str = os.getenv("CHANGE_TIMESTAMP")
    if change_timestamp_str:
        change_ts = float(change_timestamp_str)
    else:
        # Default to a reasonable test timestamp if not provided
        change_ts = time.time() - (BASELINE_DAYS + OBSERVE_DAYS/2) * 86400
    
    now = time.time()
    state = None
    state_path = Path(STATE_FILE)
    
    try:
        state = json.load(open(state_path, encoding="utf-8"))
    except Exception:
        pass

    if state is None:
        # Collect baseline metrics before the change
        baseline_start = change_ts - BASELINE_DAYS * 86400
        baseline_end = change_ts
        base = metrics(baseline_start, baseline_end)
        
        # Save initial state
        experiment_state = {
            "change_ts": change_ts, 
            "observe_until": change_ts + OBSERVE_DAYS * 86400,
            "baseline": base, 
            "reported": False
        }
        
        state_path.parent.mkdir(parents=True, exist_ok=True)
        json.dump(experiment_state, open(state_path, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        
        print(f"Compaction experiment: baseline recorded (cost ${base['cost_per_day']:.2f}/day, "
              f"compaction ${base['compaction_cost_per_day']:.2f}/day, calls {int(base['compaction_calls'])})")
        return 0

    if state.get("reported"):
        return 0
    
    if now < state.get("observe_until", 0):
        return 0

    # Collect metrics after the change
    after = metrics(state["change_ts"], now)
    base = state["baseline"]
    
    # Calculate differences
    d_cost = after["cost_per_day"] - base["cost_per_day"]
    d_comp = after["compaction_cost_per_day"] - base["compaction_cost_per_day"]
    
    # Determine verdict
    verdict = "better" if d_cost < 0 else "worse"
    
    print("📊 Compaction policy experiment results:")
    print(f"  daily cost: ${base['cost_per_day']:.2f} → ${after['cost_per_day']:.2f} ({d_cost:+.2f}) — {verdict}")
    print(f"  compaction cost: ${base['compaction_cost_per_day']:.2f} → ${after['compaction_cost_per_day']:.2f} ({d_comp:+.2f})")
    print(f"  compaction calls: {int(base['compaction_calls'])} → {int(after['compaction_calls'])}")
    print(f"  cache/input ratio: ×{base['cache_ratio']:.0f} → ×{after['cache_ratio']:.0f}")
    
    # Update state to mark as reported
    state["reported"] = True
    state["after"] = after
    json.dump(state, open(state_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    
    return 0


if __name__ == "__main__":
    raise SystemExit(main())