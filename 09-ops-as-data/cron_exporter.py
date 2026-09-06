#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cron_exporter.py — scheduled jobs as living documentation.

Reads a scheduler's job list (JSON) and renders a markdown "watch table":
which job runs when, with or without an LLM agent, where it delivers, what it
is for, and who watches it. The point: the ops documentation (`05-cron-of-crons`)
should never drift from the actual jobs — generate it instead of writing it.

Input schema (see jobs.example.json): an array of
{
  "id": "ab12cd34", "name": "morning train digest",
  "schedule": "0 6 * * 1-5",        // raw cron expression
  "agent": false,                   // false => no-LLM script job
  "deliver": "topic: commutes",
  "notes": "freshness: Mon-Fri only; not supervised",
  "watcher": "operator"             // who checks it, optional
}

Usage:
  python3 cron_exporter.py --jobs jobs.example.json --out WATCH-TABLE.md

The linter pair (`07-fresh-prompt-linter`) guards the *agent* jobs' prompts;
this exporter guards the *schedule* documentation.
"""
import argparse
import json
from datetime import datetime


def humanize(schedule: str) -> str:
    """Best-effort human read of a cron expression; falls back to raw."""
    parts = schedule.split()
    if len(parts) != 5:
        return schedule  # e.g. absolute one-shot ISO timestamps
    minute, hour, dom, mon, dow = parts
    days = {"0": "Sun", "1": "Mon", "2": "Tue", "3": "Wed",
            "4": "Thu", "5": "Fri", "6": "Sat", "7": "Sun"}

    def _step(v: str) -> str | None:
        return v[2:] if v.startswith("*/") else None

    if _step(minute):
        return f"every {_step(minute)} min"
    if _step(hour):
        return f"every {_step(hour)} h"
    if hour == "*" and minute == "*":
        return "every minute"
    if hour == "*":
        return f"minute {minute} of every hour"
    try:
        time_s = f"{int(hour):02d}:{int(minute):02d} UTC"
    except ValueError:
        time_s = f"{hour}:{minute} UTC"
    when = []
    if dow in days:
        when.append(days[dow])
    elif dow == "*":
        when.append("every day")
    elif dow == "1-5":
        when.append("Mon–Fri")
    elif dow == "1-7":
        when.append("Mon–Sun")
    if dom != "*":
        when.append(f"day {dom} of month")
    return time_s + " " + ", ".join(when) if when else time_s


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", required=True, help="JSON file with the job list")
    ap.add_argument("--out", default="WATCH-TABLE.md")
    args = ap.parse_args()

    with open(args.jobs, encoding="utf-8") as f:
        jobs = json.load(f)

    lines = []
    lines.append("# Watch table (auto-generated)")
    lines.append(f"> Generated {datetime.now():%Y-%m-%d %H:%M} from the job list — do not edit by hand;")
    lines.append("> re-run the exporter after any schedule change. See `05-cron-of-crons` for the rules.")
    lines.append("")
    lines.append("| Job | Runs (UTC) | Agent | Delivers | Notes | Watcher |")
    lines.append("|---|---|---|---|---|---|")

    agent_jobs = []
    for j in sorted(jobs, key=lambda x: (x.get("schedule", ""), x.get("name", ""))):
        name = j.get("name", "?")
        if j.get("agent", True):
            agent_jobs.append(name)
        lines.append("| {} | {} | {} | {} | {} | {} |".format(
            name,
            humanize(j.get("schedule", "?")),
            "yes" if j.get("agent", True) else "no (script)",
            j.get("deliver", "local"),
            j.get("notes", "").replace("|", "/"),
            j.get("watcher", "—"),
        ))

    lines.append("")
    lines.append("## Freshness rules")
    lines.append("- Mon–Fri jobs on Saturday are CORRECT, not an incident.")
    lines.append("- A job delivering 'local' never messages the user — its output feeds a downstream job.")
    lines.append("- No-LLM jobs print nothing when healthy (empty stdout = silence = zero cost).")
    lines.append("")
    lines.append(f"**LLM-agent jobs:** {len(agent_jobs)} — {', '.join(agent_jobs) if agent_jobs else 'none'}.")
    lines.append("Every agent job's prompt must pass `07-fresh-prompt-linter` before shipping.")

    with open(args.out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"wrote {args.out}: {len(jobs)} jobs")


if __name__ == "__main__":
    main()
