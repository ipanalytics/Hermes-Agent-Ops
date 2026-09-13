#!/usr/bin/env python3
"""Sample recent agent outputs for a blind-spot audit.

Automation accepts work by rules. Rules have a blind spot: the fraction of answers that look fine to
the checker and are wrong. You cannot see that fraction from inside the pipeline, and you cannot
judge it by reading the failures — the missing work is in the successes. So: draw a random sample of recent
outputs, redact the local paths and identifiers, and hand them to a strong model with a rubric.

    sample_outputs.py --dir ~/.hermes/cron/output --days 7 --count 12 --out blindspot_sample.md

The sample file and its manifest are deliberately boring: they exist so a weekly job can judge them
and report a rate, not so anyone reads them by hand.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import time
from pathlib import Path

REDACTIONS = [
    (r"/home/[A-Za-z0-9._-]+", "<home>"),
    (r"/var/lib/[A-Za-z0-9._/-]+", "<var>"),
    (r"\b\d{1,3}(?:\.\d{1,3}){3}(?!\d)", "<ip>"),
    (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?!\w)", "<mail>"),
    (r"\b(?:sk|pk|ghp|gho)_[A-Za-z0-9]{8,}", "<secret>"),
    (r"\bsk-or-v1-[A-Za-z0-9]{8,}", "<secret>"),
    (r"\b-?\d{1,2}\.\d{6,}\b", "<coord>"),
]


def redact(text: str) -> str:
    for pattern, repl in REDACTIONS:
        text = re.sub(pattern, repl, text)
    return text


def collect(root: Path, days: int, count: int, seed: int, max_chars: int, skip: set[str] | None = None) -> list[dict]:
    cutoff = time.time() - days * 86400
    skip = skip or set()
    candidates = [p for p in root.rglob("*")
                  if p.is_file() and p.name not in skip and p.stat().st_mtime >= cutoff and p.stat().st_size > 200]
    rng = random.Random(seed)
    rng.shuffle(candidates)
    picked = []
    for path in candidates[: count * 3]:
        if len(picked) >= count:
            break
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        picked.append({"job": path.parent.name, "file": path.name,
                       "when": time.strftime("%Y-%m-%d %H:%M", time.localtime(path.stat().st_mtime)),
                       "excerpt": redact(text[:max_chars])})
    return picked


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--count", type=int, default=12)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--max-chars", type=int, default=1200)
    ap.add_argument("--out", default="blindspot_sample.md")
    args = ap.parse_args()

    root = Path(args.dir).expanduser()
    out_name = Path(args.out).name
    picked = collect(root, args.days, args.count, args.seed, args.max_chars,
                     skip={out_name, Path(out_name).with_suffix(".json").name})
    lines = [f"# Blind-spot sample ({len(picked)} outputs, last {args.days} days)", ""]
    for n, item in enumerate(picked, 1):
        lines += [f"## Sample {n} — job `{item['job']}`, {item['when']}", "", "```", item["excerpt"], "```", ""]
    Path(args.out).write_text("\n".join(lines), encoding="utf-8")
    Path(args.out).with_suffix(".json").write_text(json.dumps(picked, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"выборка готова: {len(picked)} из {args.days} дн. → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
