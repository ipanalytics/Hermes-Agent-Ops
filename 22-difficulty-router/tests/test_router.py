#!/usr/bin/env python3
"""Offline tests: tier verdicts and the refusal to make mechanical work more expensive."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import difficulty_router as dr  # noqa: E402


class VerdictTest(unittest.TestCase):
    def test_mechanical_job_is_plain(self) -> None:
        tier, _ = dr.verdict({"runs": 10, "median_completion": 120, "p90_completion": 200, "error_rate": 0.0}, {})
        self.assertEqual(tier, "plain")

    def test_long_outputs_are_reasoning(self) -> None:
        tier, _ = dr.verdict({"runs": 10, "median_completion": 2500, "p90_completion": 5200, "error_rate": 0.0}, {})
        self.assertEqual(tier, "reasoning")

    def test_error_heavy_is_reasoning(self) -> None:
        tier, _ = dr.verdict({"runs": 10, "median_completion": 300, "p90_completion": 400, "error_rate": 0.4}, {})
        self.assertEqual(tier, "reasoning")

    def test_too_few_runs_not_classified(self) -> None:
        tier, why = dr.verdict({"runs": 1, "median_completion": 10, "p90_completion": 10, "error_rate": 0.0}, {})
        self.assertEqual(tier, "mid")
        self.assertIn("мало прогонов", why)


class RouterRunTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        recs = []
        for _ in range(5):   # mechanical job on a cheaper-token model: repinning it to a pricier
            # tier would repeat a real mistake, so the router must refuse
            recs.append({"ts": now, "job_id": "mech", "model": "cheap-old", "prompt_tokens": 500, "completion_tokens": 100})
        for _ in range(5):   # analytical job on the cheap model
            recs.append({"ts": now, "job_id": "deep", "model": "plain-flash", "prompt_tokens": 4000, "completion_tokens": 5000})
        (self.root / "audit.jsonl").write_text("\n".join(json.dumps(r) for r in recs), encoding="utf-8")
        (self.root / "jobs.json").write_text(json.dumps([
            {"id": "mech", "name": "mech", "model": "cheap-old"},
            {"id": "deep", "name": "deep", "model": "plain-flash"}]), encoding="utf-8")
        cfg = json.loads((HERE.parent / "examples" / "prices.json").read_text(encoding="utf-8"))
        (self.root / "prices.json").write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def run_tool(self) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(HERE.parent / "difficulty_router.py"),
                               "--jobs", str(self.root / "jobs.json"), "--audit", str(self.root / "audit.jsonl"),
                               "--prices", str(self.root / "prices.json")], capture_output=True, text=True,
                              cwd=str(self.root))

    def test_making_mechanical_work_pricier_is_refused(self) -> None:
        proc = self.run_tool()
        refused = [ln for ln in proc.stdout.splitlines() if "отказ" in ln]
        self.assertTrue(refused, proc.stdout)
        self.assertIn("mech", refused[0])

    def test_expensive_model_on_mechanical_work_is_downgraded(self) -> None:
        (self.root / "jobs.json").write_text(json.dumps([{"id": "mech", "name": "mech", "model": "reasoning"}]),
                                             encoding="utf-8")
        proc = self.run_tool()
        self.assertIn("mech", proc.stdout)
        self.assertIn("plain-flash", proc.stdout)

    def test_cheap_job_doing_deep_work_is_upgraded(self) -> None:
        proc = self.run_tool()
        self.assertIn("deep", proc.stdout)
        self.assertIn("reasoning", proc.stdout)


if __name__ == "__main__":
    unittest.main()
