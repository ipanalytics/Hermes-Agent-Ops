#!/usr/bin/env python3
"""A decision-relevant briefing assembled from local state, for injection into a job's context.

Scheduled agents start with an empty head: no memory of what was decided, what broke yesterday, or
what is waiting on a human. Re-reading everything to rebuild that costs tokens on every run. This
tool compiles a short brief from local files — open work items, recent changes, health counters,
unresolved failures — and writes it where a job can read it, or prints it so a scheduler can store
it as the job's own context.

    briefing.py --config examples/briefing.json            # print + write
    briefing.py --config examples/briefing.json --quiet     # write only
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path


def tail_lines(path: Path, n: int, width: int = 200) -> list[str]:
    if not path.exists():
        return []
    lines = [ln.strip() for ln in path.read_text(encoding="utf-8", errors="ignore").splitlines() if ln.strip()]
    out = []
    for ln in lines[:n]:
        out.append(ln if len(ln) <= width else ln[: width - 1] + "…")
    return out


def open_items(path: Path, statuses: tuple[str, ...], limit: int) -> list[str]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    items = data.get("items", data if isinstance(data, list) else [])
    out = []
    for item in items:
        if item.get("status") in statuses:
            out.append(f"[{item['status']}] {item.get('title', '?')}: {item.get('next_step', '')}")
    return out[:limit]


def counters(path: Path) -> str:
    if not path.exists():
        return "нет данных"
    data = json.loads(path.read_text(encoding="utf-8"))
    problems = data.get("problems") or []
    return f"проблем {len(problems)}" if isinstance(problems, list) else str(problems)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))

    L: list[str] = [f"# Briefing {time.strftime('%Y-%m-%d %H:%M')} UTC", ""]
    if cfg.get("work_items"):
        L += ["## Open work"] + [f"- {x}" for x in open_items(Path(cfg["work_items"]),
                                                             tuple(cfg.get("work_statuses", ["candidate", "trying"])),
                                                             cfg.get("work_limit", 8))] + [""]
    if cfg.get("changes_log"):
        L += ["## Recent changes"] + [f"- {x}" for x in tail_lines(Path(cfg["changes_log"]), cfg.get("changes_limit", 5))] + [""]
    if cfg.get("health_files"):
        L += ["## Health"]
        for name, path in cfg["health_files"].items():
            L.append(f"- {name}: {counters(Path(path))}")
        L.append("")
    if cfg.get("failure_jobs"):
        raw = json.loads(Path(cfg["failure_jobs"]).read_text(encoding="utf-8"))
        raw = raw if isinstance(raw, list) else raw.get("jobs", [])
        bad = [j for j in raw if j.get("last_error")]
        if bad:
            L += ["## Unresolved failures"] + [f"- {j.get('name', j['id'])}: {str(j['last_error'])[:120]}" for j in bad[:5]] + [""]

    text = "\n".join(L).rstrip() + "\n"
    if cfg.get("out_path"):
        Path(cfg["out_path"]).write_text(text, encoding="utf-8")
    if not args.quiet:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
