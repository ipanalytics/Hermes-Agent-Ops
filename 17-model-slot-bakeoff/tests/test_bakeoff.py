#!/usr/bin/env python3
"""Offline tests for bakeoff.py — no network calls.

Run either way:
    python3 tests/test_bakeoff.py
    pytest tests/test_bakeoff.py
"""
import importlib.util
import json
import pathlib
import sys
import urllib.error

BAKEOFF = pathlib.Path(__file__).resolve().parents[1] / "bakeoff.py"
spec = importlib.util.spec_from_file_location("bakeoff", BAKEOFF)
bakeoff = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bakeoff)


def test_extract_code_prefers_the_fenced_block():
    answer = "Here you go:\n```python\nprint(1)\n```\ntrailing prose"
    assert bakeoff.extract_code(answer) == "print(1)"


def test_extract_code_falls_back_to_the_whole_answer():
    assert bakeoff.extract_code("print(2)") == "print(2)"


def test_grade_passes_a_correct_solution():
    assert bakeoff.grade("def f():\n    return 7\n", "from solution import f\nassert f() == 7") == "pass"


def test_grade_reports_a_failing_solution():
    verdict = bakeoff.grade("def f():\n    return 8\n", "from solution import f\nassert f() == 7")
    assert verdict.startswith("fail:")


def test_grade_reports_import_errors_instead_of_crashing():
    verdict = bakeoff.grade("", "from solution import missing\nassert missing")
    assert verdict.startswith("fail:")


def test_grade_without_a_test_is_not_graded():
    assert bakeoff.grade("anything", None) == "not graded"


def test_candidates_get_labels_and_reject_missing_models(tmp_path):
    path = tmp_path / "c.json"
    path.write_text(json.dumps([{"model": "vendor/model-a"}]), encoding="utf-8")
    assert bakeoff.load_candidates(path)[0]["label"] == "vendor/model-a"
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps([{"label": "no model"}]), encoding="utf-8")
    try:
        bakeoff.load_candidates(bad)
        raise AssertionError("expected SystemExit")
    except SystemExit:
        pass


def test_tasks_default_to_numbered_names(tmp_path):
    path = tmp_path / "t.jsonl"
    path.write_text('{"prompt": "p"}\n', encoding="utf-8")
    tasks = bakeoff.load_tasks(path)
    assert tasks[0]["name"] == "task-1"


def test_http_error_body_is_kept_for_the_404_routing_case():
    import io
    exc = urllib.error.HTTPError(
        "https://example.invalid", 404, "Not Found", {}, io.BytesIO(
            b'{"error":{"message":"No allowed providers are available for the selected model"}}'))
    text = bakeoff.describe_http_error(exc)
    assert text.startswith("HTTP 404:")
    assert "No allowed providers" in text


def test_print_table_shows_errors_for_failed_candidates():
    import contextlib
    import io
    results = [{
        "label": "broken", "model": "vendor/x", "provider_pin": None, "extra": None,
        "tasks": [{"name": "t", "error": "HTTP 404: no providers", "latency_s": 0.2}],
        "totals": {"tasks": 1, "passed": 0, "cost_usd": 0.0, "avg_cost_per_task_usd": 0.0,
                   "avg_latency_s": 0.2, "completion_tokens": 0},
    }]
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        bakeoff.print_table(results)
    out = buffer.getvalue()
    assert "broken" in out and "no providers" in out


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            import tempfile
            tmp = pathlib.Path(tempfile.mkdtemp())
            try:
                if "tmp_path" in fn.__code__.co_varnames[:fn.__code__.co_argcount]:
                    fn(tmp)
                else:
                    fn()
                print(f"ok   {name}")
            except AssertionError as exc:
                failures += 1
                print(f"FAIL {name}: {exc}")
    print("all good" if not failures else f"{failures} failure(s)")
    sys.exit(1 if failures else 0)
