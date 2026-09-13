#!/usr/bin/env python3
"""lanes — worktree lanes + an acceptance gate for parallel writers.

Problem this solves: several agents editing the same checkout silently overwrite each
other, and the orchestrator only has the agents' own reports ("done, tests pass"). Here
every mutating lane gets its own git worktree, and a card is closed only with evidence
produced by the orchestrator: commit ids, the diff stat, and the exit code of a verify
command re-run inside the lane.

Usage:
  lanes.py new    REPO lane-a lane-b            # create worktrees + branches
  lanes.py status REPO                          # per lane: commits, dirty files, diff stat
  lanes.py gate   REPO [--cmd "pytest -q"]      # re-run verification inside every lane
  lanes.py merge  REPO --into integration [--include-failed]
  lanes.py report REPO                          # evidence JSON (path printed)

Worktrees live in REPO/.worktrees/<lane>; branches are lane/<lane>.
Exit codes: 0 ok, 1 lane failures/conflict, 2 usage/git error.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

EVIDENCE_DIR = ".worktrees"


def git(repo: str, *args: str, check: bool = True, cwd: str | None = None):
    proc = subprocess.run(["git", *args], cwd=cwd or repo, capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()[:300]}")
    return proc


def repo_root(repo: str) -> str:
    out = git(repo, "rev-parse", "--show-toplevel", check=False)
    if out.returncode != 0:
        raise SystemExit(f"not a git repository: {repo}")
    return out.stdout.strip()


def head(repo: str) -> str:
    return git(repo, "rev-parse", "--short", "HEAD").stdout.strip()


def lane_dir(root: str, lane: str) -> str:
    return os.path.join(root, EVIDENCE_DIR, lane)


def cmd_new(args) -> int:
    root = repo_root(args.repo)
    base = args.base or head(root)
    os.makedirs(os.path.join(root, EVIDENCE_DIR), exist_ok=True)
    # Ignore the lane tree via .git/info/exclude, not .gitignore: it keeps lane checkouts
    # out of `git status` for THIS clone without adding an uncommitted file to the repo.
    entry = f"{EVIDENCE_DIR}/"
    try:
        git_dir = git(root, "rev-parse", "--git-dir").stdout.strip()
        exclude = os.path.join(git_dir if os.path.isabs(git_dir) else os.path.join(root, git_dir),
                               "info", "exclude")
        os.makedirs(os.path.dirname(exclude), exist_ok=True)
        existing = open(exclude).read() if os.path.exists(exclude) else ""
        if entry not in existing:
            with open(exclude, "a") as fh:
                fh.write(("" if existing.endswith("\n") or not existing else "\n") + entry + "\n")
    except (OSError, RuntimeError):
        pass
    created = []
    for lane in args.lanes:
        path = lane_dir(root, lane)
        branch = f"lane/{lane}"
        if os.path.exists(path):
            created.append({"lane": lane, "path": path, "branch": branch, "note": "exists"})
            continue
        git(root, "worktree", "add", "-b", branch, path, base)
        created.append({"lane": lane, "path": path, "branch": branch,
                        "base": base, "note": "created"})
    print(json.dumps({"repo": root, "base": base, "lanes": created}, indent=2))
    return 0


def _lane_list(root: str) -> list[str]:
    base = os.path.join(root, EVIDENCE_DIR)
    if not os.path.isdir(base):
        return []
    return sorted(d for d in os.listdir(base) if os.path.isdir(os.path.join(base, d)))


def lane_status(root: str, lane: str, base_ref: str) -> dict:
    path = lane_dir(root, lane)
    branch = git(path, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    commits = git(path, "log", "--oneline", f"{base_ref}..HEAD", check=False).stdout.strip()
    # --name-only / --others are unambiguous; porcelain column slicing is not.
    dirty = [f for f in git(path, "diff", "--name-only", base_ref, check=False).stdout.split()
             if f]
    untracked = [f for f in git(path, "ls-files", "--others", "--exclude-standard",
                               check=False).stdout.split() if f]
    diff = git(path, "diff", "--stat", base_ref, check=False).stdout.strip()
    return {
        "lane": lane,
        "path": path,
        "branch": branch,
        "commits": commits.splitlines(),
        "commit_count": len(commits.splitlines()),
        "dirty_files": dirty,
        "untracked_files": untracked,
        "diff_stat": diff.splitlines()[-1] if diff else "",
        "diff_detail": diff,
        "head": head(path),
    }


def cmd_status(args) -> int:
    root = repo_root(args.repo)
    # Default baseline is the MAIN checkout's HEAD — inside a lane, "HEAD" is the lane's
    # own tip and would report zero commits.
    base = args.base or head(root)
    lanes = args.lanes or _lane_list(root)
    payload = [lane_status(root, lane, base) for lane in lanes]
    if args.json:
        # --json means machine consumers only: no human lines, parseable stdout.
        print(json.dumps(payload, indent=2))
        return 0
    for item in payload:
        print(f"{item['lane']:<12} {item['head']:<10} commits={item['commit_count']:<3} "
              f"dirty={len(item['dirty_files']):<3} {item['diff_stat']}")
    return 0


def detect_verify(repo: str) -> str | None:
    """Project verify recipe: hermes verify manifest, then the obvious stack markers."""
    manifest = os.path.join(repo, ".hermes", "environment.json")
    if os.path.exists(manifest):
        try:
            data = json.load(open(manifest))
            for key in ("test", "test_command", "commands"):
                value = data.get(key) if isinstance(data, dict) else None
                if isinstance(value, str) and value.strip():
                    return value
                if isinstance(value, list) and value:
                    return " && ".join(str(v) for v in value)
        except Exception:
            pass
    if os.path.exists(os.path.join(repo, "pytest.ini")) or \
       os.path.exists(os.path.join(repo, "tests")) or \
       any(f.startswith("test_") and f.endswith(".py") for f in os.listdir(repo)):
        return "python3 -m pytest -q"
    pkg = os.path.join(repo, "package.json")
    if os.path.exists(pkg):
        try:
            scripts = json.load(open(pkg)).get("scripts", {})
            if "test" in scripts:
                return "npm test --silent"
        except Exception:
            pass
    return None


def cmd_gate(args) -> int:
    root = repo_root(args.repo)
    lanes = args.lanes or _lane_list(root)
    results = []
    for lane in lanes:
        path = lane_dir(root, lane)
        command = args.cmd or detect_verify(path)
        if not command:
            results.append({"lane": lane, "gate": None, "passed": None,
                            "note": "no verify command detected — pass --cmd"})
            print(f"{lane:<12} GATE: none detected (pass --cmd)")
            continue
        started = time.time()
        proc = subprocess.run(command, cwd=path, shell=True, capture_output=True, text=True,
                              timeout=args.timeout)
        tail = (proc.stdout + proc.stderr).strip().splitlines()[-12:]
        passed = proc.returncode == 0
        results.append({"lane": lane, "gate": command, "passed": passed,
                        "exit_code": proc.returncode, "seconds": round(time.time() - started, 1),
                        "output_tail": tail})
        if args.json:
            continue
        print(f"{lane:<12} GATE {'PASS' if passed else 'FAIL'} ({command}) "
              f"exit={proc.returncode} {round(time.time() - started, 1)}s")
        for line in tail[-4:]:
            print(f"             | {line}")
    failed = [r for r in results if r["passed"] is False]
    if args.json:
        print(json.dumps(results, indent=2))
    return 1 if failed else 0


def cmd_merge(args) -> int:
    root = repo_root(args.repo)
    target = args.into
    lanes = args.lanes or _lane_list(root)
    git(root, "rev-parse", "--verify", target, check=False)
    has_target = git(root, "rev-parse", "--verify", target, check=False).returncode == 0
    if has_target:
        git(root, "checkout", target)
    else:
        git(root, "checkout", "-b", target)
    merged, conflicts = [], []
    for lane in lanes:
        branch = f"lane/{lane}"
        if git(root, "rev-parse", "--verify", branch, check=False).returncode != 0:
            continue
        proc = git(root, "merge", "--no-ff", "-m", f"merge {branch} (lane {lane})", branch,
                   check=False)
        if proc.returncode == 0:
            merged.append({"lane": lane, "commit": head(root),
                           "summary": proc.stdout.strip().splitlines()[:2]})
            print(f"merged {lane} -> {target} ({head(root)})")
        else:
            conflicts.append({"lane": lane, "stderr": proc.stderr.strip()[:400]})
            git(root, "merge", "--abort", check=False)
            print(f"CONFLICT merging {lane} — aborted, lane stays isolated")
            break
    print(json.dumps({"target": target, "merged": merged, "conflicts": conflicts}, indent=2))
    return 1 if conflicts else 0


def cmd_report(args) -> int:
    root = repo_root(args.repo)
    base = args.base or head(root)
    lanes = args.lanes or _lane_list(root)
    evidence = {"repo": root, "generated": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "base": base, "lanes": []}
    for lane in lanes:
        item = lane_status(root, lane, base)
        item["gate"] = None
        evidence["lanes"].append(item)
    out_dir = os.path.join(root, EVIDENCE_DIR)
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"evidence-{time.strftime('%Y%m%d-%H%M%S')}.json")
    with open(path, "w") as fh:
        json.dump(evidence, fh, indent=2, ensure_ascii=False)
    print(json.dumps({"evidence": path, "lanes": len(evidence["lanes"])}, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="worktree lanes + acceptance gate")
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p):
        p.add_argument("repo")
        p.add_argument("lanes", nargs="*")
        p.add_argument("--base", default=None)
        p.add_argument("--json", action="store_true")

    p_new = sub.add_parser("new")
    p_new.add_argument("repo")
    p_new.add_argument("lanes", nargs="+")
    p_new.add_argument("--base", default=None)
    p_new.set_defaults(func=cmd_new)

    p_status = sub.add_parser("status")
    common(p_status)
    p_status.set_defaults(func=cmd_status)

    p_gate = sub.add_parser("gate")
    common(p_gate)
    p_gate.add_argument("--cmd", default=None)
    p_gate.add_argument("--timeout", type=int, default=900)
    p_gate.set_defaults(func=cmd_gate)

    p_merge = sub.add_parser("merge")
    common(p_merge)
    p_merge.add_argument("--into", required=True)
    p_merge.set_defaults(func=cmd_merge)

    p_report = sub.add_parser("report")
    common(p_report)
    p_report.set_defaults(func=cmd_report)

    args = parser.parse_args()
    try:
        return args.func(args)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
