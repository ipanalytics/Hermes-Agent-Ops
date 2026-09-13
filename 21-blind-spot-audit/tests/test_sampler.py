#!/usr/bin/env python3
"""Offline tests: window selection, redaction, deterministic sampling."""
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
TOOL = HERE.parent / "sample_outputs.py"


class SamplerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        for job, text in [("job-a", "report from /home/alex/secret 192.168.1.10"), ("job-b", "x" * 400)]:
            d = self.root / job
            d.mkdir()
            (d / "run.md").write_text(text * 5, encoding="utf-8")
        old = self.root / "job-c"
        old.mkdir()
        p = old / "old.md"
        p.write_text("y" * 400, encoding="utf-8")
        stale = time.time() - 40 * 86400
        os.utime(p, (stale, stale))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def sample(self, *extra: str) -> tuple[subprocess.CompletedProcess, Path]:
        (self.root / "out").mkdir(exist_ok=True)
        out = self.root / "out" / "sample.md"
        proc = subprocess.run([sys.executable, str(TOOL), "--dir", str(self.root), "--days", "7",
                               "--count", "5", "--out", str(out), *extra], capture_output=True, text=True)
        return proc, out

    def test_old_outputs_excluded(self) -> None:
        _, out = self.sample()
        text = out.read_text(encoding="utf-8")
        self.assertNotIn("job-c", text)
        self.assertIn("job-a", text)

    def test_own_output_is_not_resampled(self) -> None:
        self.sample()
        _, out = self.sample()
        manifest = json.loads(out.with_suffix(".json").read_text(encoding="utf-8"))
        self.assertTrue(all(item["file"] != "sample.md" for item in manifest))

    def test_paths_and_ips_redacted(self) -> None:
        _, out = self.sample()
        text = out.read_text(encoding="utf-8")
        self.assertNotIn("/home/alex", text)
        self.assertNotIn("192.168.1.10", text)
        self.assertIn("<home>", text)
        self.assertIn("<ip>", text)

    def test_sampling_is_deterministic_for_a_seed(self) -> None:
        _, out1 = self.sample("--seed", "7")
        first = out1.read_text(encoding="utf-8")
        _, out2 = self.sample("--seed", "7")
        self.assertEqual(first, out2.read_text(encoding="utf-8"))

    def test_manifest_written(self) -> None:
        _, out = self.sample()
        manifest = json.loads(out.with_suffix(".json").read_text(encoding="utf-8"))
        self.assertTrue(manifest)
        self.assertIn("job", manifest[0])


if __name__ == "__main__":
    unittest.main()
