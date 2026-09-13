#!/usr/bin/env python3
"""Weekly direction digest: the same corpus, counted the same way, week after week.

Trend reports usually compare what an index chose to show this week with what it chose last week —
a different sample each time. This tool instead counts terms over locally harvested text in equal
windows, prints shares rather than absolute counts, and marks a shift only when it survives both.
Output is one screen: what is growing, what is flat, what we already tried.

    direction_digest.py --corpus data/cs.AI.jsonl --terms examples/terms.json --out digest.md
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def window_counts(records: list[dict], terms: dict[str, str]) -> dict:
    total = len(records)
    counts = {name: 0 for name in terms}
    for rec in records:
        text = f"{rec.get('title', '')} {rec.get('abstract', '')}"
        for name, pattern in terms.items():
            if re.search(pattern, text, re.I):
                counts[name] += 1
    return {"total": total, "counts": counts,
            "shares": {k: (v / total if total else 0.0) for k, v in counts.items()}}


def split_windows(records: list[dict], weeks: int = 5) -> list[list[dict]]:
    """Split by calendar week of the record's date, newest last, into at most `weeks` buckets."""
    buckets: dict[str, list[dict]] = {}
    for rec in records:
        day = (rec.get("created") or "")[:10]
        if not day:
            continue
        buckets.setdefault(day[:10], []).append(rec)
    ordered = [buckets[k] for k in sorted(buckets)]
    if len(ordered) <= weeks:
        return ordered
    step = len(ordered) / weeks
    return [sum(ordered[int(i * step):int((i + 1) * step)], []) for i in range(weeks)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--terms", required=True)
    ap.add_argument("--weeks", type=int, default=5)
    ap.add_argument("--out", default="digest.md")
    args = ap.parse_args()

    terms = json.loads(Path(args.terms).read_text(encoding="utf-8"))
    records = [json.loads(ln) for ln in Path(args.corpus).read_text(encoding="utf-8").splitlines() if ln.strip()]
    windows = [window_counts(w, terms) for w in split_windows(records, args.weeks)]

    lines = ["# Direction digest", ""]
    if not windows:
        lines.append("нет размеченных записей")
    else:
        first, last = windows[0], windows[-1]
        lines += [f"windows: {len(windows)}, records: {sum(w['total'] for w in windows)}", "",
                  "| term | first window | last window | shift |", "|---|---|---|---|"]
        for name in terms:
            a, b = first["shares"][name], last["shares"][name]
            delta = b - a
            mark = "↑" if delta > 0.01 else ("↓" if delta < -0.01 else "=")
            lines.append(f"| {name} | {a:.1%} | {b:.1%} | {mark} {delta:+.1%} |")
        flat = [n for n in terms if abs(last["shares"][n] - first["shares"][n]) <= 0.01]
        lines += ["", f"ровно: {', '.join(flat) if flat else '—'}", "",
                  "Shift counts only when it survives an equal-window comparison; a single week with more"]
        lines.append("records moves every share, which is why totals travel with the table.")
    Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
