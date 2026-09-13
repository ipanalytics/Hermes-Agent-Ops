#!/usr/bin/env python3
"""Task-level health for scheduled agents: did the work happen, not just did the process exit.

A cron that exits 0 and delivers nothing looks identical to a quiet week, until you notice three
days later that no digest arrived. These checks are the difference between "the job ran" and "the
job produced what it promises", and they stay silent while everything is fine.

    task_evals.py --jobs jobs.json --output-dir cron/output --config examples/task_evals.json

Checks (declared in config, no code to add one):
    output_fresh   a job's newest output is younger than N hours, bigger than M bytes,
                   and matches a pattern at least K times (e.g. three cards in a digest)
    no_failures    no job in the set has a failure streak longer than the allowed limit
    queue_clear    no items stuck in a non-terminal state for more than N hours
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path


def newest_output(output_dir: Path, job_id: str) -> Path | None:
    d = output_dir / job_id
    if not d.exists():
        return None
    files = sorted((p for p in d.iterdir() if p.is_file()), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def check_output_fresh(spec: dict, jobs: dict, output_dir: Path) -> list[str]:
    problems = []
    for job_id in spec["jobs"]:
        jid = job_id if isinstance(job_id, str) else job_id.get("id")
        name = jobs.get(jid, jid)
        max_age = spec.get("max_age_hours", 30)
        min_bytes = spec.get("min_bytes", 500)
        pattern = spec.get("pattern")
        min_hits = spec.get("min_hits", 1)
        path = newest_output(output_dir, jid)
        if path is None:
            problems.append(f"{name}: нет выводов вообще")
            continue
        age_h = (time.time() - path.stat().st_mtime) / 3600
        if age_h > max_age:
            problems.append(f"{name}: последний вывод {age_h:.0f} ч назад (лимит {max_age} ч)")
            continue
        if path.stat().st_size < min_bytes:
            problems.append(f"{name}: вывод подозрительно мал ({path.stat().st_size} б)")
            continue
        if pattern:
            text = path.read_text(encoding="utf-8", errors="ignore")
            hits = len(re.findall(pattern, text, re.M))
            if hits < min_hits:
                problems.append(f"{name}: в выводе {hits} совпадений, нужно {min_hits}")
    return problems


def check_no_failures(spec: dict, raw_jobs: list[dict]) -> list[str]:
    limit = spec.get("max_streak", 2)
    problems = []
    for job in raw_jobs:
        streak = job.get("failure_streak") or 0
        if streak > limit:
            problems.append(f"{job.get('name', job.get('id'))}: {streak} провалов подряд")
    return problems


def check_queue_clear(spec: dict) -> list[str]:
    cmd = spec["command"]
    limit = spec.get("max_recent_stale", 3)
    try:
        out = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=spec.get("timeout_s", 120)).stdout
    except Exception as exc:  # noqa: BLE001
        return [f"очередь не проверена: {type(exc).__name__}"]
    stale = len(re.findall(spec.get("stale_pattern", r"\bstale\b"), out))
    if stale > limit:
        return [f"в очереди {stale} зависших элементов (лимит {limit})"]
    return []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", required=True)
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--config", required=True)
    ap.add_argument("--report", default="task_evals.json")
    args = ap.parse_args()

    raw = json.loads(Path(args.jobs).read_text(encoding="utf-8"))
    raw = raw if isinstance(raw, list) else raw.get("jobs", [])
    jobs = {j["id"]: j.get("name", "?") for j in raw}
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))

    checks, problems = [], []
    for spec in config.get("checks", []):
        kind, out = spec.get("kind"), []
        if kind == "output_fresh":
            out = check_output_fresh(spec, jobs, Path(args.output_dir))
        elif kind == "no_failures":
            out = check_no_failures(spec, raw)
        elif kind == "queue_clear":
            out = check_queue_clear(spec)
        checks.append({"check": spec.get("id", kind), "problems": out})
        problems += out

    Path(args.report).write_text(json.dumps({"checked_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                             "problems": problems, "checks": checks},
                                            ensure_ascii=False, indent=1), encoding="utf-8")
    if problems:
        print(f"❗️ Задачные эвалы: проблем {len(problems)}")
        for p in problems:
            print(f"  • {p}")
        return 1
    return 0  # silence: the jobs did what they promised


if __name__ == "__main__":
    raise SystemExit(main())
