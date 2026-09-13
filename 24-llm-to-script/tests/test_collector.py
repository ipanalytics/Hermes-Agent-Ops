#!/usr/bin/env python3
"""Offline tests: dedup by stable key, explicit ranking, state growth, audit shortlist."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import collector as col  # noqa: E402
import token_audit as ta  # noqa: E402


class CollectorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.rules = json.loads((HERE.parent / "examples" / "rules.json").read_text(encoding="utf-8"))
        self.feed = json.loads((HERE.parent / "examples" / "feed.json").read_text(encoding="utf-8"))

    def test_ranking_prefers_wanted_year_and_quality(self) -> None:
        cards, _ = col.collect(self.feed, {"seen": []}, self.rules, top=2)
        titles = [c["title"] for c in cards]
        self.assertIn("Big Film (2026)", titles)
        self.assertNotIn("Cam Rip (2026)", titles)   # negative weight keeps it out

    def test_dedup_by_key_removes_repeats(self) -> None:
        first, state = col.collect(self.feed, {"seen": []}, self.rules, top=6)
        second, _ = col.collect(self.feed, state, self.rules, top=6)
        self.assertEqual(len(first), 4)
        self.assertEqual(second, [])

    def test_state_stores_keys_not_content(self) -> None:
        _, state = col.collect(self.feed, {"seen": []}, self.rules, top=6)
        self.assertTrue(all(len(k) == 16 for k in state["seen"]))

    def test_cli_writes_artifact_and_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "state.json").write_text('{"seen": []}', encoding="utf-8")
            proc = subprocess.run([sys.executable, str(HERE.parent / "collector.py"),
                                   "--input", str(HERE.parent / "examples" / "feed.json"),
                                   "--state", str(root / "state.json"),
                                   "--out", str(root / "cards.md"), "--top", "3",
                                   "--rules", str(HERE.parent / "examples" / "rules.json")],
                                  capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0)
            self.assertEqual(proc.stdout.strip(), "карточек: 3")
            self.assertIn("description: ⟨model fills one sentence⟩", (root / "cards.md").read_text(encoding="utf-8"))


class TokenAuditTest(unittest.TestCase):
    def test_instruction_score(self) -> None:
        self.assertGreaterEqual(ta.instruction_score("Fetch the feed, parse it, if it fails retry"), 3)

    def test_shortlist_flags_large_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "jobs.json").write_text(json.dumps([
                {"id": "fat", "name": "fat", "prompt": "fetch the page, parse it, otherwise retry"},
                {"id": "lean", "name": "lean", "prompt": "write a haiku"}]))
            (root / "audit.jsonl").write_text("\n".join(json.dumps(
                {"ts": "2026-09-13T00:00:00", "job_id": jid, "prompt_tokens": pt, "completion_tokens": 100})
                for jid, pt in [("fat", 900000), ("fat", 800000), ("lean", 300)]), encoding="utf-8")
            proc = subprocess.run([sys.executable, str(HERE.parent / "token_audit.py"),
                                   "--jobs", str(root / "jobs.json"), "--audit", str(root / "audit.jsonl"),
                                   "--top", "5"], capture_output=True, text=True)
            self.assertIn("кандидат на скрипт", proc.stdout)
            self.assertIn("fat", proc.stdout)


if __name__ == "__main__":
    unittest.main()
