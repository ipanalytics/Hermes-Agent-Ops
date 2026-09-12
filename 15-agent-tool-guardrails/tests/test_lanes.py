#!/usr/bin/env python3
"""End-to-end test for lanes.py (worktree lanes + acceptance gate) on a scratch repo.

Run: python3 /home/hermes/.hermes/scripts/tests/test_lanes.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

LANES = os.environ.get("LANES_PY") or os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lanes.py")
FAILS = []


def run(*args, cwd=None, expect=0):
    proc = subprocess.run([sys.executable, LANES, *args], cwd=cwd, capture_output=True, text=True)
    if proc.returncode != expect:
        FAILS.append(f"{' '.join(args)} -> exit {proc.returncode}, expected {expect}\n"
                     f"{(proc.stdout + proc.stderr)[:400]}")
    return proc


def check(condition, label):
    print(f"{'PASS' if condition else 'FAIL'}  {label}")
    if not condition:
        FAILS.append(label)


def sh(cmd, cwd):
    return subprocess.run(cmd, cwd=cwd, shell=True, capture_output=True, text=True)


def main():
    root = tempfile.mkdtemp(prefix="lanes-demo-")
    sh("git init -q && git config user.email t@t && git config user.name t && "
       "echo 'v1' > app.py && git add -A && git commit -qm init", root)

    run("new", root, "alpha", "beta")
    check(os.path.isdir(os.path.join(root, ".worktrees", "alpha")), "worktree alpha created")
    check(os.path.isdir(os.path.join(root, ".worktrees", "beta")), "worktree beta created")

    # two writers in separate checkouts: alpha's check passes, beta's fails
    sh("echo 'alpha feature' > feature_a.py && echo 'print(1)' > check.py && "
       "git add -A && git commit -qm 'alpha: feature_a'", os.path.join(root, ".worktrees", "alpha"))
    sh("echo 'beta feature' > feature_b.py && printf 'raise SystemExit(1)\\n' > check_b.py && "
       "git add -A && git commit -qm 'beta: feature_b'", os.path.join(root, ".worktrees", "beta"))
    sh("echo 'uncommitted' >> app.py", os.path.join(root, ".worktrees", "beta"))

    status = run("status", root, "--json")
    payload = json.loads(status.stdout)
    by_lane = {item["lane"]: item for item in payload}
    check(by_lane["alpha"]["commit_count"] == 1, "alpha reports 1 commit")
    check(by_lane["beta"]["commit_count"] == 1, "beta reports 1 commit")
    check("app.py" in by_lane["beta"]["dirty_files"], "beta dirty file detected (uncommitted work)")
    check(by_lane["alpha"]["head"] != by_lane["beta"]["head"], "lanes have independent heads")

    gate_a = run("gate", root, "alpha", "--cmd", "python3 check.py")
    check("PASS" in gate_a.stdout, "gate: alpha PASS")
    gate_b = run("gate", root, "beta", "--cmd", "python3 check_b.py", expect=1)
    check("FAIL" in gate_b.stdout, "gate: beta FAIL (failing check caught)")

    gate_json = run("gate", root, "alpha", "--cmd", "python3 check.py", "--json")
    check(json.loads(gate_json.stdout)[0]["exit_code"] == 0, "gate --json is parseable")

    merge = run("merge", root, "--into", "integration")
    check(merge.returncode == 0, "merge into integration succeeded")
    check(os.path.exists(os.path.join(root, "feature_a.py")), "alpha work landed in integration")
    check(os.path.exists(os.path.join(root, "feature_b.py")), "beta work landed in integration")

    report = run("report", root)
    evidence_path = json.loads(report.stdout)["evidence"]
    evidence = json.load(open(evidence_path))
    check(bool(evidence["lanes"][0]["head"]), "evidence json has per-lane heads")
    check(os.path.isfile(evidence_path), "evidence file written")

    # conflict path: both lanes touch the same file
    run("new", root, "gamma", "delta", "--base", "integration")
    sh("echo gamma >> app.py && git add -A && git commit -qm gamma",
       os.path.join(root, ".worktrees", "gamma"))
    sh("echo delta >> app.py && git add -A && git commit -qm delta",
       os.path.join(root, ".worktrees", "delta"))
    conflict = run("merge", root, "--into", "integration", expect=1)
    check("CONFLICT" in conflict.stdout, "conflict detected and reported")
    check(sh("git status --porcelain", root).stdout.strip() == "", "merge was aborted cleanly")

    shutil.rmtree(root, ignore_errors=True)
    print(f"\n{'ALL PASSED' if not FAILS else str(len(FAILS)) + ' FAILURES'}")
    for f in FAILS:
        print(" -", f)
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
