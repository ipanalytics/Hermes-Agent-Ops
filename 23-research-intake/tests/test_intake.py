#!/usr/bin/env python3
"""Offline tests: fixture parsing, resumption token, local counting, equal-window digest."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import oai_harvest as oh          # noqa: E402
import direction_digest as dd     # noqa: E402

FIX = HERE.parent / "examples" / "oai_fixture.xml"
TERMS = HERE.parent / "examples" / "terms.json"


class ParseTest(unittest.TestCase):
    def test_parses_records_and_skips_deleted(self) -> None:
        records, token = oh.parse_records(FIX.read_text(encoding="utf-8"))
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["id"], "oai:arXiv.org:2609.01345")
        self.assertIn("blind spots", records[0]["title"])
        self.assertEqual(token, "token-abc")

    def test_fixture_mode_writes_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "h.jsonl"
            proc = subprocess.run([sys.executable, str(HERE.parent / "oai_harvest.py"),
                                   "--fixture", str(FIX), "--out", str(out)], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0)
            self.assertEqual(len(out.read_text(encoding="utf-8").strip().splitlines()), 1)


class CountTest(unittest.TestCase):
    def test_counts_terms_locally(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            corpus = Path(tmp) / "c.jsonl"
            corpus.write_text("\n".join(json.dumps(r) for r in [
                {"id": "1", "title": "cheap verifier", "abstract": "cost of inference and budget"},
                {"id": "2", "title": "swarm of agents", "abstract": "multi-agent debate"},
                {"id": "3", "title": "nothing", "abstract": "unrelated"}] + [{"id": "4", "title": "x", "abstract": "y"}] * 1),
                              encoding="utf-8")
            result = oh.count_terms(corpus, json.loads(TERMS.read_text(encoding="utf-8")))
            self.assertEqual(result["records"], 4)
            self.assertEqual(result["counts"]["cost/tokens"], 1)
            self.assertEqual(result["counts"]["multi-agent"], 1)
            self.assertGreater(result["shares"]["cost/tokens"], 0)


class DigestTest(unittest.TestCase):
    def test_equal_windows_and_shares(self) -> None:
        records = []
        for week, terms_text in [("2026-08-01", "eval"), ("2026-08-08", "eval"),
                                 ("2026-08-15", "eval cost"), ("2026-08-22", "eval cost")]:
            for i in range(3):
                records.append({"id": f"{week}-{i}", "created": week, "title": terms_text, "abstract": ""})
        windows = dd.split_windows(records, 4)
        self.assertEqual(len(windows), 4)
        counts = dd.window_counts(windows[-1], json.loads(TERMS.read_text(encoding="utf-8")))
        self.assertEqual(counts["total"], 3)
        self.assertEqual(counts["counts"]["cost/tokens"], 3)


if __name__ == "__main__":
    unittest.main()
