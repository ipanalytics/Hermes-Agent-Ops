#!/usr/bin/env python3
"""skill-library-janitor — a periodic static check for a library of agent skill files.

A skill library rots quietly: a file the skill points at gets renamed, a script stops
compiling after an interpreter upgrade, the frontmatter loses its description, a directory
and its declared name drift apart. None of this fails loudly — it is discovered in the
middle of real work, when the skill is loaded and the path it needs is not there.

This tool walks the library and reports only what is checkably wrong: broken references,
code that no longer compiles, frontmatter that is missing or out of bounds. It does not
judge wording and it does not call a model, so it costs nothing to run monthly.

    python3 janitor.py --skills-dir ~/.hermes/skills --report report.json
    python3 janitor.py --skills-dir ./skills --quiet --strict    # cron: silent unless dirty
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time

HOME = pathlib.Path.home()
PATH_RE = re.compile(r"(?:~|/home/[a-z0-9_-]+)/[A-Za-z0-9._/-]+\.(?:py|sh|md|json|db|sqlite|yaml|yml|toml|txt)")
SCRIPT_RE = re.compile(r"\bscripts/([A-Za-z0-9._-]+\.(?:py|sh))")
PLACEHOLDER_RE = re.compile(r"[*{}<>\u2026]|\bN\b|\bX\b|\$")
DESC_MIN, DESC_MAX = 20, 200
MAX_PATH_FINDINGS = 6


def split_frontmatter(text: str):
    """Returns (fields, body). Only top-level `key: value` lines are read."""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end < 0:
        return {}, text
    fields = {}
    for line in text[3:end].splitlines():
        if ":" in line and not line[:1].isspace():
            key, value = line.split(":", 1)
            fields[key.strip()] = value.strip().strip("\"'")
    return fields, text[end + 4:]


def resolve(raw: str, skill_dir: pathlib.Path, home: pathlib.Path):
    """Candidate locations for a referenced artefact: absolute, under home, or library-wide."""
    if raw.startswith("~/"):
        yield home / raw[2:]
    elif raw.startswith("/"):
        yield pathlib.Path(raw)
    else:
        yield skill_dir / raw
        yield home / raw


def check_paths(body: str, skill_dir: pathlib.Path, home: pathlib.Path):
    """Returns (problems, count of paths that live outside the home tree).

    `scripts/foo.py` in a skill usually means the library-wide scripts directory, not a
    folder inside the skill itself, so three locations are tried before calling it broken.
    """
    problems, external = [], 0
    for raw in sorted(set(PATH_RE.findall(body))):
        if PLACEHOLDER_RE.search(raw):
            continue
        candidates = list(resolve(raw, skill_dir, home))
        if any(c.exists() for c in candidates):
            continue
        if raw.startswith("~/") or raw.startswith(str(home)):
            problems.append(f"missing path: {raw}")
        else:
            external += 1
    for name in sorted(set(SCRIPT_RE.findall(body))):
        if PLACEHOLDER_RE.search(name):
            continue
        places = [skill_dir / "scripts" / name, skill_dir / name, home / "scripts" / name]
        if not any(p.exists() for p in places):
            problems.append(f"missing script: {name}")
    return problems[:MAX_PATH_FINDINGS], external


def check_code(skill_dir: pathlib.Path, limit: int = 40):
    problems = []
    for path in sorted(skill_dir.rglob("*.py"))[:limit]:
        if "__pycache__" in path.parts:
            continue
        try:
            compile(path.read_text(encoding="utf-8", errors="replace"), str(path), "exec")
        except SyntaxError as exc:
            problems.append(f"{path.name}: syntax error at line {exc.lineno}")
    if shutil.which("bash"):
        for path in sorted(skill_dir.rglob("*.sh"))[:20]:
            done = subprocess.run(["bash", "-n", str(path)], capture_output=True, text=True)
            if done.returncode != 0:
                tail = (done.stderr.strip().splitlines() or ["bash -n failed"])[-1]
                problems.append(f"{path.name}: {tail[:90]}")
    return problems


def audit_library(dirs, home: pathlib.Path = HOME, check_syntax: bool = True):
    """Walks every SKILL.md under the given directories. Returns a list of findings."""
    findings = []
    files = []
    for root in dirs:
        files += sorted(pathlib.Path(root).rglob("SKILL.md"))
    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        fields, body = split_frontmatter(text)
        problems = []
        name = fields.get("name", "")
        if not name:
            problems.append("frontmatter has no name")
        elif name != path.parent.name:
            problems.append(f"name '{name}' does not match directory '{path.parent.name}'")
        description = fields.get("description", "")
        if not description:
            problems.append("frontmatter has no description")
        elif not DESC_MIN <= len(description) <= DESC_MAX:
            problems.append(f"description is {len(description)} chars (expected {DESC_MIN}-{DESC_MAX})")
        path_problems, external = check_paths(body, path.parent, home)
        problems += path_problems
        if check_syntax:
            problems += check_code(path.parent)
        if problems:
            findings.append({"skill": str(path.parent), "problems": problems,
                             "external_paths_missing": external})
    return {"checked": len(files), "findings": findings,
            "external_paths_missing": sum(f["external_paths_missing"] for f in findings)}


def report_text(result: dict, limit: int = 25) -> str:
    if not result["findings"]:
        return ""
    lines = [f"skill library: {result['checked']} checked, {len(result['findings'])} need attention"
             f" (paths outside this machine, not counted as broken: {result['external_paths_missing']})"]
    for item in result["findings"][:limit]:
        lines.append(f"- {item['skill']}: " + "; ".join(item["problems"]))
    if len(result["findings"]) > limit:
        lines.append(f"... and {len(result['findings']) - limit} more")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="static hygiene check for a skill library")
    parser.add_argument("--skills-dir", action="append", required=True)
    parser.add_argument("--home", default=str(HOME))
    parser.add_argument("--report", default="", help="write the machine-readable result here")
    parser.add_argument("--quiet", action="store_true", help="print nothing when clean (cron mode)")
    parser.add_argument("--strict", action="store_true", help="exit 1 when findings exist")
    parser.add_argument("--no-code", action="store_true", help="skip compile/shell checks")
    args = parser.parse_args(argv)

    result = audit_library(args.skills_dir, home=pathlib.Path(args.home),
                           check_syntax=not args.no_code)
    if args.report:
        payload = dict(result, checked_at=time.time())
        pathlib.Path(args.report).write_text(
            json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    text = report_text(result)
    if text:
        print(text)
    elif not args.quiet:
        print(f"skill library: {result['checked']} checked, nothing broken")
    if args.strict and result["findings"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
