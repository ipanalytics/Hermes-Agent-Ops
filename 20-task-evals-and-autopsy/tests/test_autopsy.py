#!/usr/bin/env python3
"""Offline tests: failure classification, dedup of seen failures, task-eval freshness and cards."""
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
POST = HERE.parent / "postmortem.py"
TASKS = HERE.parent / "task_evals.py"


class ClassifierTest(unittest.TestCase):
    def test_classes(self) -> None:
        sys.path.insert(0, str(HERE.parent))
        import postmortem  # noqa: PLC0415
        cases = {
            "chat not found": "доставка",
            "429 rate limit exceeded": "лимит модели",
            "database is locked": "состояние/база",
            "connection timed out": "сеть",
            "Traceback (most recent call last):": "скрипт",
            "что-то неизвестное": "прочее",
        }
        for text, expected in cases.items():
            self.assertEqual(postmortem.classify(text)[0], expected, text)


class PostmortemTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def run_tool(self) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(POST), "--jobs", str(self.root / "jobs.json"),
                               "--journal", str(self.root / "j.md"), "--seen", str(self.root / "seen.json")],
                              capture_output=True, text=True)

    def test_new_failure_reported_once(self) -> None:
        (self.root / "jobs.json").write_text(json.dumps([
            {"id": "a", "name": "digest", "last_status": "error", "last_error": "429 rate limit"}]),
            encoding="utf-8")
        first = self.run_tool()
        self.assertIn("лимит модели", first.stdout)
        second = self.run_tool()
        self.assertEqual(second.stdout.strip(), "")

    def test_healthy_jobs_are_silent(self) -> None:
        (self.root / "jobs.json").write_text(json.dumps([{"id": "a", "name": "ok", "last_status": "ok"}]),
                                             encoding="utf-8")
        self.assertEqual(self.run_tool().stdout.strip(), "")


class TaskEvalsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "output" / "job-1").mkdir(parents=True)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write(self, text: str, age_hours: float = 1.0) -> None:
        p = self.root / "output" / "job-1" / "run.md"
        p.write_text(text, encoding="utf-8")
        old = time.time() - age_hours * 3600
        os.utime(p, (old, old))

    def run_tool(self) -> subprocess.CompletedProcess:
        cfg = {"checks": [{"id": "cards", "kind": "output_fresh", "jobs": ["job-1"], "max_age_hours": 30,
                           "min_bytes": 20, "pattern": "^\\s*(?:№\\s*\\d+|\\d+)[).]?\\s", "min_hits": 3}]}
        (self.root / "cfg.json").write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
        (self.root / "jobs.json").write_text(json.dumps([{"id": "job-1", "name": "digest"}]), encoding="utf-8")
        return subprocess.run([sys.executable, str(TASKS), "--jobs", str(self.root / "jobs.json"),
                               "--output-dir", str(self.root / "output"), "--config", str(self.root / "cfg.json"),
                               "--report", str(self.root / "report.json")], capture_output=True, text=True)

    def test_healthy_digest_is_silent(self) -> None:
        self.write("№1. a\n№2. b\n№3. c\n" + "x" * 40)
        proc = self.run_tool()
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout.strip(), "")

    def test_missing_cards_reported(self) -> None:
        self.write("№1. только одна карточка\n" + "x" * 40)
        proc = self.run_tool()
        self.assertEqual(proc.returncode, 1)
        self.assertIn("совпадений", proc.stdout)

    def test_stale_output_reported(self) -> None:
        self.write("№1. a\n№2. b\n№3. c\n" + "x" * 40, age_hours=50)
        proc = self.run_tool()
        self.assertIn("ч назад", proc.stdout)


if __name__ == "__main__":
    unittest.main()
