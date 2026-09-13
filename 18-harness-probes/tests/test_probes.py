#!/usr/bin/env python3
"""Offline tests for probes.py — no network, no real harness."""
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
TOOL = HERE.parent / "probes.py"


class ProbeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "data").mkdir()
        (self.root / "cron" / "output").mkdir(parents=True)
        self.env = dict(os.environ, HARNESS_HOME=str(self.root))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write_set(self, probes: list[dict]) -> None:
        (self.root / "data" / "probe_set.json").write_text(json.dumps({"probes": probes}), encoding="utf-8")

    def run_tool(self, mode: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(TOOL), mode], capture_output=True, text=True, env=self.env)

    def test_fresh_file_passes(self) -> None:
        (self.root / "data" / "report.json").write_text("x" * 600, encoding="utf-8")
        self.write_set([{"id": "r", "kind": "file_fresh", "path": f"{self.root}/data/report.json",
                         "max_age_hours": 1, "min_bytes": 100}])
        self.assertEqual(self.run_tool("run").returncode, 0)

    def test_stale_file_fails(self) -> None:
        p = self.root / "data" / "report.json"
        p.write_text("x" * 600, encoding="utf-8")
        old = time.time() - 48 * 3600
        os.utime(p, (old, old))
        self.write_set([{"id": "r", "kind": "file_fresh", "path": str(p), "max_age_hours": 2}])
        proc = self.run_tool("run")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("старый", proc.stdout)

    def test_regression_detected_against_baseline(self) -> None:
        target = self.root / "data" / "flag.txt"
        target.write_text("ok", encoding="utf-8")
        self.write_set([{"id": "f", "kind": "file_fresh", "path": str(target), "max_age_hours": 24}])
        self.assertEqual(self.run_tool("accept").returncode, 0)
        target.unlink()
        proc = self.run_tool("check")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("РЕГРЕССИЯ", proc.stdout)

    def test_silent_script_expectations(self) -> None:
        quiet = self.root / "quiet.py"
        quiet.write_text("raise SystemExit(0)\n", encoding="utf-8")
        loud = self.root / "loud.py"
        loud.write_text("print('hello')\n", encoding="utf-8")
        self.write_set([
            {"id": "q", "kind": "script_silent", "script": str(quiet), "expect": "empty"},
            {"id": "l", "kind": "script_silent", "script": str(loud), "expect": "nonempty"},
        ])
        self.assertEqual(self.run_tool("run").returncode, 0)
        self.write_set([{"id": "q", "kind": "script_silent", "script": str(quiet), "expect": "nonempty"}])
        self.assertEqual(self.run_tool("run").returncode, 1)

    def test_secret_scan_finds_token(self) -> None:
        (self.root / "cron" / "output" / "run.md").write_text("token: sk-test-placeholder-0000", encoding="utf-8")
        self.write_set([{"id": "s", "kind": "secrets_clean", "dir": f"{self.root}/cron/output", "glob": "*.md"}])
        proc = self.run_tool("run")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("секрет", proc.stdout)

    def test_text_match_counts_cards(self) -> None:
        digest = self.root / "data" / "last_digest.md"
        digest.write_text("№1. a\n№2. b\n", encoding="utf-8")
        self.write_set([{"id": "c", "kind": "text_match", "path": str(digest),
                         "pattern": "^\\s*(?:№\\s*\\d+|\\d+)[).]?\\s", "min_count": 3}])
        self.assertEqual(self.run_tool("run").returncode, 1)


if __name__ == "__main__":
    unittest.main()
