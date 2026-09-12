#!/usr/bin/env python3
"""Tests for the dataset-dedupe step in tuner.py.

Run either way:
    python3 tests/test_dedupe.py     # standalone, no dependencies
    pytest tests/test_dedupe.py      # if pytest is around

The point of these cases: a duplicated input must never reach the optimizer twice, and a
group whose copies disagree on the label must be reported instead of silently averaged.
"""
import importlib.util
import pathlib
import sys

TUNER = pathlib.Path(__file__).resolve().parents[1] / "tuner.py"
spec = importlib.util.spec_from_file_location("tuner", TUNER)
tuner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tuner)


def test_plain_duplicate_is_collapsed():
    rows = [{"input": "a", "answer": "x"}, {"input": "a", "answer": "x"},
            {"input": "b", "answer": "y"}, {"input": "c", "answer": "z"}]
    unique, stats = tuner.dedupe_dataset(rows)
    assert [r["input"] for r in unique] == ["a", "b", "c"]
    assert stats["rows_in"] == 4 and stats["rows_kept"] == 3
    assert stats["duplicates_removed"] == 1 and stats["conflict_groups"] == 0


def test_whitespace_and_case_are_normalised():
    rows = [{"input": "  Hello   world ", "answer": "x"},
            {"input": "hello world", "answer": "x"}]
    unique, stats = tuner.dedupe_dataset(rows)
    assert len(unique) == 1 and stats["duplicates_removed"] == 1
    assert unique[0]["input"] == "  Hello   world "  # first spelling is preserved


def test_conflicting_labels_go_to_majority_and_are_reported():
    rows = [{"input": "q", "answer": "hermes-ecosystem-ops"},
            {"input": "q", "answer": "home-infra-ops"},
            {"input": "q", "answer": "hermes-ecosystem-ops"}]
    unique, stats = tuner.dedupe_dataset(rows)
    assert len(unique) == 1 and unique[0]["answer"] == "hermes-ecosystem-ops"
    assert stats["conflict_groups"] == 1
    assert stats["conflicts"][0]["labels"] == {"hermes-ecosystem-ops": 2, "home-infra-ops": 1}
    assert stats["conflicts"][0]["kept"] == "hermes-ecosystem-ops"


def test_tie_keeps_first_occurrence():
    rows = [{"input": "q", "answer": "first"},
            {"input": "q", "answer": "second"}]
    unique, _ = tuner.dedupe_dataset(rows)
    assert unique[0]["answer"] == "first"


def test_order_is_stable_and_no_row_is_lost():
    rows = [{"input": f"q{i % 3}", "answer": "x"} for i in range(9)]
    unique, stats = tuner.dedupe_dataset(rows)
    assert [r["input"] for r in unique] == ["q0", "q1", "q2"]
    assert stats["rows_in"] == 9 and stats["rows_kept"] == 3


def test_conflict_samples_are_capped():
    rows = [{"input": f"q{i}", "answer": "a"} for i in range(7)]
    rows += [{"input": f"q{i}", "answer": "b"} for i in range(7)]
    _, stats = tuner.dedupe_dataset(rows, max_conflict_samples=3)
    assert stats["conflict_groups"] == 7 and len(stats["conflicts"]) == 3


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"ok   {name}")
            except AssertionError as exc:
                failures += 1
                print(f"FAIL {name}: {exc}")
    print("all good" if not failures else f"{failures} failure(s)")
    sys.exit(1 if failures else 0)
