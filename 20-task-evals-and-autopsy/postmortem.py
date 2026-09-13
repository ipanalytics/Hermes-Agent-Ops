#!/usr/bin/env python3
"""Failure autopsy: classify what broke and say what to do, without a human reading logs first.

A job list already records the last error per job; what it does not do is tell anyone what class of
failure that was. This tool reads the job list, matches the error text against known classes, writes
one line per new failure to a journal, and prints only failures it has not reported before — so a
recurring known problem does not spam, and a new one is visible immediately.

    postmortem.py --jobs jobs.json --journal postmortems.md --seen seen.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from pathlib import Path

# Each class: (label, matcher, advice). Order matters — first match wins.
CLASSES: list[tuple[str, str, str]] = [
    ("доставка", r"chat not found|blocked|forbidden|delivery|sendMessage|thread",
     "проверить цель доставки и права бота на этот чат/топик"),
    ("лимит модели", r"rate limit|429|quota|too many requests|overloaded",
     "разнести по времени, сменить upstream или ждать окна"),
    ("состояние/база", r"session storage|state database|database is locked|disk I/O|corrupt|wal",
     "проверить место и блокировки базы, затем health-check рантайма"),
    ("сеть", r"timeout|timed out|connection reset|dns|unreachable|SSL",
     "повторить; при повторе — проверить маршрут/прокси"),
    ("скрипт", r"Traceback|SyntaxError|NameError|command not found|No such file|exit code [1-9]",
     "прочитать последнюю строку трассы, править скрипт; повтор бессмыслен"),
]


def classify(text: str) -> tuple[str, str]:
    for label, pattern, advice in CLASSES:
        if re.search(pattern, text, re.I):
            return label, advice
    return "прочее", "разобрать вручную: класс не распознан"


def fingerprint(job_id: str, text: str) -> str:
    return hashlib.sha1(f"{job_id}|{text[:160]}".encode("utf-8")).hexdigest()[:12]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", required=True)
    ap.add_argument("--journal", default="postmortems.md")
    ap.add_argument("--seen", default="postmortem_seen.json")
    args = ap.parse_args()

    raw = json.loads(Path(args.jobs).read_text(encoding="utf-8"))
    raw = raw if isinstance(raw, list) else raw.get("jobs", [])
    seen_path = Path(args.seen)
    seen = set(json.loads(seen_path.read_text(encoding="utf-8")).get("fingerprints", [])) if seen_path.exists() else set()

    new_entries = []
    for job in raw:
        err = job.get("last_error") or job.get("last_delivery_error")
        if not err or job.get("last_status") in (None, "ok", "silent"):
            continue
        label, advice = classify(str(err))
        fp = fingerprint(job["id"], str(err))
        if fp in seen:
            continue
        seen.add(fp)
        new_entries.append((job.get("name", job["id"]), label, str(err).replace("\n", " ")[:160], advice, fp))

    if not new_entries:
        return 0

    print("🩺 Разбор падений (автоматически):")
    journal = Path(args.journal)
    with journal.open("a", encoding="utf-8") as fh:
        for name, label, err, advice, fp in new_entries:
            print(f"  • {name} [{label}]: {err}\n    → {advice}")
            fh.write(f"- {time.strftime('%Y-%m-%d %H:%M')} · {name} · [{label}] · {err}\n  совет: {advice}\n")

    seen_path.write_text(json.dumps({"fingerprints": sorted(seen)}, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
