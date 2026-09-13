#!/usr/bin/env python3
"""Static check: does a scheduled job's prompt reference a tool its toolset does not include?

Agent runtimes let you restrict which tools a job may use, which cuts the fixed prompt prefix on
every single turn. The failure mode is silent: prune the wrong toolset and the job keeps running
while the capability it needed disappears. This tool reads a job list and a toolset→regex map and
reports the mismatches before they cost a run.

    toolsets_audit.py --jobs jobs.json --map examples/toolset_map.json
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", required=True)
    ap.add_argument("--map", required=True, dest="map_path")
    args = ap.parse_args()

    jobs = json.loads(Path(args.jobs).read_text(encoding="utf-8"))
    jobs = jobs if isinstance(jobs, list) else jobs.get("jobs", [])
    mapping = json.loads(Path(args.map_path).read_text(encoding="utf-8"))

    problems = []
    for job in jobs:
        enabled = job.get("enabled_toolsets")
        if not enabled:
            continue
        prompt = job.get("prompt") or ""
        for tool, pattern in mapping.items():
            if tool in enabled:
                continue
            hit = re.search(pattern, prompt, re.I)
            if hit:
                problems.append((job.get("name", job.get("id", "?")), tool, hit.group(0)))

    if not problems:
        print("toolsets match the prompts")
        return 0
    print(f"possible missing toolsets: {len(problems)}")
    for name, tool, token in problems:
        print(f"  {name}: нет «{tool}», а в промпте — «{token}»")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
