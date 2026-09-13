#!/usr/bin/env python3
"""A budget cap that acts instead of alerting.

Alerts assume somebody is awake. A scheduled agent burns money at 04:00 as happily as at noon, so
the useful control is not a threshold you read about later — it is a threshold that pauses the
most expensive work and releases it on schedule.

Reads a usage ledger (JSONL: one record per model call with a timestamp, a job id and token
counts), sums the current UTC day, and when the cap is exceeded pauses the N most expensive jobs
by invoking a command template. `--resume` releases exactly the jobs that this tool paused.

    budget_guard.py                 # check; act if over cap
    budget_guard.py --dry-run       # print what would be paused
    budget_guard.py --resume        # release paused jobs

Nothing is paused twice: the set of jobs this tool stopped lives in its own state file.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

CONFIG = Path(os.environ.get("BUDGET_CONFIG", str(Path.home() / ".hermes/data/budget_guard.json")))
DEFAULT = {
    "audit_path": "~/.hermes/cron/usage_audit.jsonl",
    "state_path": "~/.hermes/data/budget_guard_state.json",
    "cap_tokens_per_day": 12_000_000,
    "top_n": 3,
    "pause_command": "hermes cron pause {job_id}",
    "resume_command": "hermes cron resume {job_id}",
}


def load_config() -> dict:
    cfg = dict(DEFAULT)
    if CONFIG.exists():
        cfg.update(json.loads(CONFIG.read_text(encoding="utf-8")))
    return cfg


def expand(p: str) -> Path:
    return Path(os.path.expanduser(str(p)))


def day_start(now: float | None = None) -> float:
    now = now or time.time()
    return now - (now % 86400)


def today_usage(audit: Path, cutoff: float) -> dict[str, int]:
    """Tokens per job for records at or after cutoff."""
    per_job: dict[str, int] = defaultdict(int)
    if not audit.exists():
        return per_job
    for line in audit.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        ts = rec.get("ts") or ""
        try:
            epoch = time.mktime(time.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S"))
        except Exception:
            continue
        if epoch < cutoff:
            continue
        tokens = rec.get("total_tokens") or ((rec.get("prompt_tokens") or 0) + (rec.get("completion_tokens") or 0))
        per_job[rec.get("job_id", "?")] += tokens
    return per_job


def run_cmd(template: str, job_id: str, dry: bool) -> bool:
    cmd = template.format(job_id=job_id)
    if dry:
        print(f"  [dry-run] {cmd}")
        return True
    try:
        return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60).returncode == 0
    except Exception:
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description="Token budget cap that pauses the most expensive jobs")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--resume", action="store_true")
    args = ap.parse_args()

    cfg = load_config()
    state_path = expand(cfg["state_path"])
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {"paused": []}

    if args.resume:
        released = []
        for job_id in state.get("paused", []):
            if run_cmd(cfg["resume_command"], job_id, args.dry_run):
                released.append(job_id)
        state["paused"] = [j for j in state.get("paused", []) if j not in released]
        state.pop("action_date", None)
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
        if released and not args.dry_run:
            print(f"возвращено в расписание: {len(released)}")
        return 0

    usage = today_usage(expand(cfg["audit_path"]), day_start())
    spent = sum(usage.values())
    cap = int(cfg["cap_tokens_per_day"])
    if spent < cap:
        return 0  # silent: under the cap

    today = time.strftime("%Y-%m-%d")
    if state.get("action_date") == today:
        return 0  # already acted today: no cascade of pauses

    already = set(state.get("paused", []))
    candidates = [(jid, tok) for jid, tok in sorted(usage.items(), key=lambda kv: -kv[1]) if jid not in already]
    chosen = [jid for jid, _ in candidates[: int(cfg["top_n"])]]
    if not chosen:
        return 0

    print(f"❗️ Бюджет: {spent:,} токенов за сутки при лимите {cap:,} — пауза {len(chosen)} самых дорогих")
    for jid in chosen:
        print(f"  • {jid}: {usage.get(jid, 0):,} токенов")
        run_cmd(cfg["pause_command"], jid, args.dry_run)
    if not args.dry_run:
        state["paused"] = list(already | set(chosen))
        state["action_date"] = today
        state["last_action"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        state["spent_at_action"] = spent
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
