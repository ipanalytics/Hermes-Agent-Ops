#!/usr/bin/env python3
"""Research Scout: fresh arXiv papers via OAI-PMH, theme filtering and acceptance voting, output for model and stable gate fingerprint.

Two modes via cron gate monitor:
  • collection (slow): OAI-PMH arXiv over window + HF votes for same days → filter by themes,
    dedup via seen journal, write data/research_scout.md and stable fingerprint string to stdout;
  • repeat call in same tick: if cache fresher than 30 minutes — use it, no network again.

If no new relevant papers, prints same string without timestamp — cron gate sees unchanged output
and mutes run (empty tick better than week gap).
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

HOME = Path.home() / ".hermes"
DATA = HOME / "data"
MD = DATA / "research_scout.md"
SEEN = DATA / "research_scout_seen.json"
CACHE = DATA / "research_scout_cache.json"
TOPIC = DATA / "research_direction.md"

WINDOW_DAYS = 6
CACHE_MINUTES = 30
MAX_ITEMS = 7

# arXiv OAI knows only top-level sets: subsets like cs:cs.AI are rejected.
SETS = ["cs"]
THEMES = {
    # strong themes: subject exactly (agent-as-service exploitation)
    "harness": r"harness|scaffold|tool[- ]use|tool call|function call|\bskills?\b|orchestrat\w+ agents?",
    "evals": r"\beval\w*|benchmark|verifier|rubric|reward model|grading|regression suite",
    "memory": r"agent memory|long[- ]term memory|memory card|context engineering|context management",
    "routing": r"model rout\w+|model select\w+|escalat\w+|cost[- ]aware|budget[- ]aware|tiered",
    "determinism": r"deterministic|workflow synthesis|program synthesis|script\w* generation|compil\w+ (?:agent|workflow)",
    "sandbox": r"sandbox|isolated execution|permission model|capability restriction",
    "agentcore": r"agentic|autonomous agent|agent workflow|LLM agent",
    # weak themes: backup only
    "cost": r"token cost|cost per (?:task|query)|latency|throughput|inference efficienc",
    "multiagent": r"multi[- ]agent|swarm|debate",
    "safety": r"guardrail|prompt injection|exfiltration",
}
STRONG = {"harness", "evals", "memory", "routing", "determinism", "sandbox", "agentcore"}


def theme_scores(title: str, abstract: str) -> tuple[dict, int]:
    """Score: title hit worth 3x abstract hit."""
    scores = {}
    low_t, low_a = title.lower(), abstract.lower()
    for name, pat in THEMES.items():
        s = 0
        if re.search(pat, low_t):
            s += 3
        if re.search(pat, low_a):
            s += 1
        if s:
            scores[name] = s
    total = sum(v for n, v in scores.items() if n in STRONG) + sum(v for n, v in scores.items() if n not in STRONG)
    return scores, total


HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; research-scout/1.0)"}
NO_NEW = "no new relevant arXiv papers"


def oai_window(days: int = WINDOW_DAYS) -> list[dict]:
    """Fresh arXiv records via OAI-PMH (legal mass delivery, unlike query API).

    arxiv_fetch.py writes records to jsonl and prints summary with file path — read file.
    Window may contain old papers (datestamp update), so year-month of id checked against current.
    """
    import subprocess

    until = datetime.now(timezone.utc).date()
    frm = until - timedelta(days=days)
    keep_prefixes = {(until.strftime("%y%m")), ((until.replace(day=1) - timedelta(days=1)).strftime("%y%m"))}
    seen_paths: list[Path] = []
    for s in SETS:
        cmd = [sys.executable, str(HOME / "scripts" / "arxiv_fetch.py"), "oai",
               "--set", s, "--from", frm.isoformat(), "--until", until.isoformat(), "--max-pages", "12"]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=240)
        except subprocess.TimeoutExpired:
            continue
        try:
            info = json.loads(r.stdout[r.stdout.find("{"):])
        except Exception:  # noqa: BLE001
            continue
        f = info.get("file")
        if f:
            seen_paths.append(Path(f))
    out: list[dict] = []
    for path in seen_paths:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                rec = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            rid = str(rec.get("id") or "")
            if rid[:4] in keep_prefixes:
                rec["published"] = f"20{rid[:2]}-{rid[2:4]}"
                out.append(rec)
    return out


def hf_votes(days: int = WINDOW_DAYS) -> dict[str, int]:
    """HF daily papers votes for window: only key-free acceptance signal available."""
    votes: dict[str, int] = {}
    try:
        latest = json.loads(urllib.request.urlopen(urllib.request.Request(
            "https://huggingface.co/api/daily_papers?limit=40", headers=HEADERS), timeout=25).read())
        for row in latest or []:
            pp = (row.get("paper") or {})
            if pp.get("id"):
                key = pp["id"].split("v")[0]
                votes[key] = max(votes.get(key, 0), int(pp.get("upvotes") or 0))
    except Exception:  # noqa: BLE001
        pass
    for i in range(days):
        day = (datetime.now(timezone.utc).date() - timedelta(days=i)).isoformat()
        try:
            url = f"https://huggingface.co/api/daily_papers?date={day}"
            data = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=25).read())
        except Exception:  # noqa: BLE001
            continue
        for row in data or []:
            p = row.get("paper") or {}
            pid, up = p.get("id"), p.get("upvotes") or 0
            if pid:
                votes[pid.split("v")[0]] = max(votes.get(pid.split("v")[0], 0), int(up))
    return votes


def collect() -> tuple[str, list[dict]]:
    seen = json.loads(SEEN.read_text(encoding="utf-8")) if SEEN.exists() else {"ids": []}
    seen_ids = set(seen.get("ids", []))
    votes = hf_votes()
    rows, fresh = oai_window(), []
    for r in rows:
        rid = (r.get("id") or "").split("v")[0]
        if not rid or rid in seen_ids:
            continue
        title = r.get("title") or ""
        abstract = r.get("abstract") or r.get("summary") or ""
        scores, total = theme_scores(title, abstract)
        if total < 3:
            continue
        tags = sorted(scores, key=lambda n: -scores[n])
        fresh.append({"id": rid, "title": re.sub(r"\s+", " ", title).strip(), "tags": tags, "score": total,
                      "votes": votes.get(rid, 0), "published": (r.get("published") or "")[:10],
                      "abstract": re.sub(r"\s+", " ", abstract)[:240],
                      "url": f"https://arxiv.org/abs/{rid}"})
    fresh.sort(key=lambda x: (x["score"], x["votes"]), reverse=True)
    picked = fresh[:MAX_ITEMS]
    # fingerprint: stable fields only, no time — otherwise cron gate triggers needlessly
    fingerprint = NO_NEW if not picked else "\n".join(f"{p['id']}|{p['score']}|{p['votes']}|{','.join(p['tags'])}" for p in picked)
    if picked:
        seen_ids |= {p["id"] for p in picked}
        SEEN.write_text(json.dumps({"ids": sorted(seen_ids)[-5000:], "updated": datetime.now(timezone.utc).date().isoformat()},
                                   ensure_ascii=False, indent=1), encoding="utf-8")
        lines = [f"# New papers in {WINDOW_DAYS} days (picked {len(picked)} from {len(fresh)} relevant)", ""]
        for i, p in enumerate(picked, 1):
            lines += [f"№{i}. {p['title']}",
                      f"    arXiv {p['id']} · {p['published']} · score {p['score']} · themes: {', '.join(p['tags'])} · HF votes: {p['votes']}",
                      f"    abstract: {p['abstract'][:200]}",
                      f"    {p['url']}",
                      "    for me: (write 1 line — what this gives my agent)",
                      ""]
        lines.append("MODEL TASK: (1) what is new and why important; (2) where to apply — module or cron; "
                     "(3) what to publish in public series; (4) one idea for future. "
                     "If reception is disputed — say directly. Reviews — no more than one per paper.")
        MD.write_text("\n".join(lines), encoding="utf-8")
    print(fingerprint)
    return fingerprint, picked


def main() -> int:
    if "-h" in sys.argv or "--help" in sys.argv:
        print(__doc__)
        return 0
    if CACHE.exists() and (time.time() - CACHE.stat().st_mtime) < CACHE_MINUTES * 60:
        print(CACHE.read_text(encoding="utf-8").strip())
        return 0
    fp, picked = collect()
    CACHE.write_text(fp + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())