#!/usr/bin/env python3
"""Offline tests: cap arithmetic, top-N selection, pause/resume idempotence, toolset matching."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
GUARD = HERE.parent / "budget_guard.py"
AUDIT_TOOL = HERE.parent / "toolsets_audit.py"


class BudgetGuardTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.audit = self.root / "usage_audit.jsonl"
        self.state = self.root / "state.json"
        self.actions = self.root / "actions.log"
        self.cfg = self.root / "config.json"
        self.cfg.write_text(json.dumps({
            "audit_path": str(self.audit), "state_path": str(self.state),
            "cap_tokens_per_day": 1000, "top_n": 2,
            "pause_command": f"echo pause {{job_id}} >> {self.actions}",
            "resume_command": f"echo resume {{job_id}} >> {self.actions}",
        }), encoding="utf-8")
        self.env = dict(os.environ, BUDGET_CONFIG=str(self.cfg))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write_usage(self, records: list[tuple[str, int]]) -> None:
        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        with self.audit.open("w", encoding="utf-8") as fh:
            for job, tokens in records:
                fh.write(json.dumps({"ts": now + ".000Z", "job_id": job, "total_tokens": tokens}) + "\n")

    def run_guard(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(GUARD), *args], capture_output=True, text=True, env=self.env)

    def test_silent_under_cap(self) -> None:
        self.write_usage([("a", 100)])
        proc = self.run_guard()
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout.strip(), "")

    def test_pauses_two_most_expensive(self) -> None:
        self.write_usage([("cheap", 100), ("mid", 500), ("dear", 900)])
        proc = self.run_guard()
        self.assertIn("пауза 2", proc.stdout)
        log = self.actions.read_text(encoding="utf-8")
        self.assertIn("pause dear", log)
        self.assertIn("pause mid", log)
        self.assertNotIn("pause cheap", log)

    def test_second_run_does_not_repause(self) -> None:
        self.write_usage([("cheap", 100), ("mid", 500), ("dear", 900)])
        self.run_guard()
        before = self.actions.read_text(encoding="utf-8").count("pause")
        self.run_guard()
        self.assertEqual(before, self.actions.read_text(encoding="utf-8").count("pause"))

    def test_resume_releases_only_what_was_paused(self) -> None:
        self.write_usage([("cheap", 100), ("mid", 500), ("dear", 900)])
        self.run_guard()
        proc = self.run_guard("--resume")
        self.assertIn("возвращено в расписание: 2", proc.stdout)
        state = json.loads(self.state.read_text(encoding="utf-8"))
        self.assertEqual(state["paused"], [])

    def test_dry_run_touches_nothing(self) -> None:
        self.write_usage([("dear", 5000)])
        proc = self.run_guard("--dry-run")
        self.assertIn("[dry-run]", proc.stdout)
        self.assertFalse(self.state.exists())


class ToolsetAuditTest(unittest.TestCase):
    def test_reports_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            jobs = root / "jobs.json"
            jobs.write_text(json.dumps([{"name": "digest", "enabled_toolsets": ["terminal"],
                                         "prompt": "fetch https://example.org and write_file the result"}]),
                            encoding="utf-8")
            proc = subprocess.run([sys.executable, str(AUDIT_TOOL), "--jobs", str(jobs),
                                   "--map", str(HERE.parent / "examples" / "toolset_map.json")],
                                  capture_output=True, text=True)
            self.assertIn("possible missing toolsets", proc.stdout)
            self.assertIn("file", proc.stdout)


if __name__ == "__main__":
    unittest.main()
