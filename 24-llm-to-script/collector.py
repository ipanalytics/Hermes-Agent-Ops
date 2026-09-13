#!/usr/bin/env python3
"""Reference collector: do the collecting deterministically, leave the writing to the model.

The expensive pattern in a scheduled agent is a model that fetches, parses, dedupes and ranks on
every run and then writes two paragraphs at the end. The cheap pattern is the reverse: a script
produces the structured artifact, the model only formats it. Same output, a fraction of the prefix.

This is the whole shape, with a pluggable source so it runs offline in tests:

    source → normalise → dedup by stable key → rank by explicit rules → write artifact + one-line summary

    collector.py --input examples/feed.json --state examples/seen.json --out cards.md --top 6
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

QUALITY_RANK = {"2160p": 3, "1080p": 2, "720p": 1}


def normalise(raw: dict) -> dict:
    """One shape for downstream code, whatever the source looked like."""
    title = (raw.get("title") or "").strip()
    return {
        "key": hashlib.sha1((raw.get("link") or title).encode("utf-8")).hexdigest()[:16],
        "title": title,
        "link": raw.get("link") or "",
        "year": raw.get("year"),
        "quality": (raw.get("quality") or "").lower(),
        "tags": [t.strip().lower() for t in (raw.get("tags") or [])],
        "published": (raw.get("published") or "")[:19],
    }


def score(item: dict, rules: dict) -> float:
    s = 0.0
    for tag, weight in rules.get("tag_weights", {}).items():
        if tag in item["tags"]:
            s += weight
    s += QUALITY_RANK.get(item["quality"], 0) * rules.get("quality_weight", 1.0)
    if item.get("year") == rules.get("want_year"):
        s += rules.get("year_weight", 1.0)
    return s


def collect(items: list[dict], state: dict, rules: dict, top: int) -> tuple[list[dict], dict]:
    seen = set(state.get("seen", []))
    fresh = [normalise(i) for i in items if normalise(i)["key"] not in seen]
    fresh.sort(key=lambda i: (-score(i, rules), i.get("published", "")), reverse=False)
    chosen = fresh[:top]
    state["seen"] = sorted(seen | {i["key"] for i in fresh})
    return chosen, state


def render(cards: list[dict]) -> str:
    lines = ["# Cards (structured artifact for the formatter)", ""]
    for n, c in enumerate(cards, 1):
        lines += [f"{n}. {c['title']}",
                  f"   link: {c['link']}",
                  f"   quality: {c['quality'] or '—'}, year: {c.get('year') or '—'}, tags: {', '.join(c['tags']) or '—'}",
                  "   description: ⟨model fills one sentence⟩", ""]
    lines += ["Formatter: keep the numbering, one sentence per card, no links in the chat message."]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--state", required=True)
    ap.add_argument("--out", default="cards.md")
    ap.add_argument("--top", type=int, default=6)
    ap.add_argument("--rules", default="examples/rules.json")
    args = ap.parse_args()

    items = json.loads(Path(args.input).read_text(encoding="utf-8"))
    state_path = Path(args.state)
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {"seen": []}
    rules = json.loads(Path(args.rules).read_text(encoding="utf-8"))

    cards, state = collect(items, state, rules, args.top)
    Path(args.out).write_text(render(cards), encoding="utf-8")
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"карточек: {len(cards)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
