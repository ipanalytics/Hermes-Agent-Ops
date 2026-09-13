#!/usr/bin/env python3
"""Deterministic acceptance probes for an agent harness.

The scaffolding around an agent changes constantly: prompts, cron schedules, guard scripts,
routing tables. Most of it has no test suite, so a change that fixes one thing quietly breaks
another. This tool makes every harness edit pass through a set of probes that already describe
known-good behaviour.

Modes:
    run     execute every probe, write a JSON report, print failures
    check   run probes and compare against the accepted baseline; a probe that used to pass
            and now fails is a regression and the process exits 1
    accept  record the current probe results as the new baseline (a deliberate act)
    list    show the probe set

Probe kinds (declared in JSON, no code needed to add one):
    file_fresh      file exists, is younger than N hours and at least M bytes
    files_no_empty  no zero-byte files under a directory
    json_keys       JSON file parses, has required keys, optional minimum length
    script_silent   run a command; expect exit 0 and (empty|nonempty|any) stdout
    text_match      file contains a pattern at least N times
    secrets_clean   no secret-looking strings in the newest N files of a directory

Env:
    HARNESS_HOME   root that ~ refers to for probe paths (default: $HOME/.hermes)
    PROBE_SET      probe set path (default: $HARNESS_HOME/data/probe_set.json)
    PROBE_STATE    directory for baseline/last-report (default: $HARNESS_HOME/data)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HOME = Path(os.environ.get("HARNESS_HOME", str(Path.home() / ".hermes")))
PROBE_SET = Path(os.environ.get("PROBE_SET", str(HOME / "data/probe_set.json")))
STATE = Path(os.environ.get("PROBE_STATE", str(HOME / "data")))
BASELINE = STATE / "probes_baseline.json"
LAST = STATE / "probes_last.json"

SECRET_PATTERNS = [
    r"\b(sk|pk)-[A-Za-z0-9]{16,}\b",
    r"\bsk-or-v1-[A-Za-z0-9]{20,}\b",
    r"\bghp_[A-Za-z0-9]{20,}\b",
    r"\bAKIA[0-9A-Z]{16}\b",
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    r"(?i)\b(password|passwd|token|api[_-]?key)\s*[:=]\s*[\"']?[^\s\"']{10,}",
]


def expand(p: str) -> Path:
    return Path(os.path.expanduser(p)).expanduser() if not p.startswith("/") else Path(p)


def probe_file_fresh(spec: dict) -> tuple[bool, str]:
    path = expand(spec["path"])
    if not path.exists():
        return False, "нет файла"
    age_h = (time.time() - path.stat().st_mtime) / 3600
    size = path.stat().st_size
    limit = spec.get("max_age_hours", 24)
    min_bytes = spec.get("min_bytes", 1)
    if age_h > limit:
        return False, f"старый: {age_h:.1f} ч > {limit} ч"
    if size < min_bytes:
        return False, f"маленький: {size} б < {min_bytes} б"
    return True, f"{size} б, {age_h:.1f} ч назад"


def probe_files_no_empty(spec: dict) -> tuple[bool, str]:
    directory = expand(spec["dir"])
    pattern = spec.get("glob", "*")
    limit = spec.get("max_empty", 0)
    if not directory.exists():
        return False, "нет каталога"
    empty = [p for p in directory.glob(pattern) if p.is_file() and p.stat().st_size == 0]
    if len(empty) > limit:
        return False, f"пустышек {len(empty)} (лимит {limit})"
    return True, "пустышек нет" if not empty else f"пустышек {len(empty)}"


def probe_json_keys(spec: dict) -> tuple[bool, str]:
    path = expand(spec["path"])
    if not path.exists():
        return False, "нет файла"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return False, f"не JSON: {type(exc).__name__}"
    for key in spec.get("required_keys", []):
        probe_obj = data
        for part in str(key).split("."):
            if isinstance(probe_obj, dict) and part in probe_obj:
                probe_obj = probe_obj[part]
            else:
                return False, f"нет ключа {key}"
    count = len(data) if isinstance(data, (list, dict)) else 1
    min_items = spec.get("min_items", 0)
    if count < min_items:
        return False, f"элементов {count} < {min_items}"
    return True, f"{count} элементов"


def probe_script_silent(spec: dict) -> tuple[bool, str]:
    script = expand(spec["script"])
    cmd = [sys.executable, str(script)] + [str(a) for a in spec.get("args", [])]
    if str(script).endswith((".sh", ".bash")):
        cmd = ["bash", str(script)] + [str(a) for a in spec.get("args", [])]
    if not script.exists():
        return False, "нет скрипта"
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=spec.get("timeout_s", 180))
    except subprocess.TimeoutExpired:
        return False, "таймаут"
    expect = spec.get("expect", "empty")
    out = (proc.stdout or "").strip()
    if proc.returncode != 0:
        return False, f"код возврата {proc.returncode}"
    if expect == "empty" and out:
        return False, f"говорит: {out.splitlines()[0][:80]}"
    if expect == "nonempty" and not out:
        return False, "молчит, а должен говорить"
    return True, "empty" if not out else "nonempty"


def probe_text_match(spec: dict) -> tuple[bool, str]:
    path = expand(spec["path"])
    if not path.exists():
        return False, "нет файла"
    text = path.read_text(encoding="utf-8", errors="ignore")
    hits = len(re.findall(spec["pattern"], text, re.M))
    need = spec.get("min_count", 1)
    if hits < need:
        return False, f"совпадений {hits} < {need}"
    return True, f"совпадений {hits}"


def probe_secrets_clean(spec: dict) -> tuple[bool, str]:
    directory = expand(spec["dir"])
    newest = int(spec.get("files", 25))
    if not directory.exists():
        return False, "нет каталога"
    files = sorted((p for p in directory.rglob(spec.get("glob", "*.md")) if p.is_file()),
                   key=lambda p: p.stat().st_mtime, reverse=True)[:newest]
    found = []
    for p in files:
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for pat in SECRET_PATTERNS:
            if re.search(pat, text):
                found.append(p.name)
                break
    if found:
        return False, f"похоже на секрет в {len(found)} файл(ах): {', '.join(found[:3])}"
    return True, f"{len(files)} файлов чисто"


KINDS = {
    "file_fresh": probe_file_fresh,
    "files_no_empty": probe_files_no_empty,
    "json_keys": probe_json_keys,
    "script_silent": probe_script_silent,
    "script": probe_script_silent,
    "text_match": probe_text_match,
    "secrets_clean": probe_secrets_clean,
}


def load_probes() -> list[dict]:
    if not PROBE_SET.exists():
        print(f"нет набора проб: {PROBE_SET}", file=sys.stderr)
        raise SystemExit(2)
    return json.loads(PROBE_SET.read_text(encoding="utf-8")).get("probes", [])


def run_all() -> list[dict]:
    results = []
    for spec in load_probes():
        kind = spec.get("kind", "script")
        fn = KINDS.get(kind)
        if fn is None:
            results.append({"id": spec.get("id", "?"), "kind": kind, "ok": False, "why": f"неизвестный вид {kind}"})
            continue
        try:
            ok, why = fn(spec)
        except Exception as exc:  # noqa: BLE001
            ok, why = False, f"исключение: {type(exc).__name__}: {exc}"
        results.append({"id": spec.get("id", "?"), "kind": kind, "title": spec.get("title", ""),
                        "ok": ok, "why": why})
    return results


def cmd_run(quiet_all_ok: bool = False) -> int:
    results = run_all()
    passed = sum(1 for r in results if r["ok"])
    STATE.mkdir(parents=True, exist_ok=True)
    LAST.write_text(json.dumps({"checked_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "total": len(results),
                                "passed": passed, "probes": results}, ensure_ascii=False, indent=1),
                    encoding="utf-8")
    failed = [r for r in results if not r["ok"]]
    if failed:
        print(f"❗️ пробы: {passed}/{len(results)}")
        for r in failed:
            print(f"  • {r.get('title') or r['id']}: {r['why']}")
        return 1
    if not quiet_all_ok:
        print(f"пробы пройдены: {passed}/{len(results)}")
    return 0


def cmd_check() -> int:
    results = run_all()
    passed = sum(1 for r in results if r["ok"])
    STATE.mkdir(parents=True, exist_ok=True)
    LAST.write_text(json.dumps({"checked_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "total": len(results),
                                "passed": passed, "probes": results}, ensure_ascii=False, indent=1),
                    encoding="utf-8")
    baseline = {}
    if BASELINE.exists():
        baseline = {p["id"]: p["ok"] for p in json.loads(BASELINE.read_text(encoding="utf-8")).get("probes", [])}
    regressions = [r for r in results if baseline.get(r["id"]) and not r["ok"]]
    failures = [r for r in results if not r["ok"]]
    if regressions:
        print(f"❗️ РЕГРЕССИЯ: пробы {passed}/{len(results)} (в базе было {sum(1 for v in baseline.values() if v)})")
        for r in regressions:
            print(f"  • {r.get('title') or r['id']}: {r['why']}")
        print("Правку не принимаем: сначала верни пробу в строй (или probes.py accept, если старое поведение устарело).")
        return 1
    if failures:
        print(f"⚠️ пробы: {passed}/{len(results)} (падения есть, но их не было и в базе)")
        for r in failures:
            print(f"  • {r.get('title') or r['id']}: {r['why']}")
        return 0
    return 0


def cmd_accept() -> int:
    results = run_all()
    STATE.mkdir(parents=True, exist_ok=True)
    BASELINE.write_text(json.dumps({"accepted_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                    "probes": results}, ensure_ascii=False, indent=1), encoding="utf-8")
    passed = sum(1 for r in results if r["ok"])
    print(f"база проб записана: {passed}/{len(results)}")
    return 0


def cmd_list() -> int:
    for spec in load_probes():
        print(f"{spec.get('id', '?'):22s} {spec.get('kind', 'script'):16s} {spec.get('title', '')}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Deterministic acceptance probes for an agent harness")
    ap.add_argument("mode", choices=["run", "check", "accept", "list"])
    args = ap.parse_args()
    return {"run": cmd_run, "check": cmd_check, "accept": cmd_accept, "list": cmd_list}[args.mode]()


if __name__ == "__main__":
    raise SystemExit(main())
