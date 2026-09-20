#!/usr/bin/env python3
"""Offline tests for consilium.py — no network, no API key.

Run either way:
    python3 tests/test_consilium.py
    pytest tests/test_consilium.py
"""
import importlib.util
import json
import pathlib
import urllib.error

MODULE = pathlib.Path(__file__).resolve().parents[1] / "consilium.py"
spec = importlib.util.spec_from_file_location("consilium", MODULE)
consilium = importlib.util.module_from_spec(spec)
spec.loader.exec_module(consilium)

NO_SLEEP = lambda _seconds: None  # noqa: E731 - keep the retry tests instant


def fake_call(answers):
    """Records (model, messages, max_tokens) and replies with the queued answers."""
    seen = []

    def call(model, messages, max_tokens):
        seen.append({"model": model, "messages": messages, "max_tokens": max_tokens})
        text = answers[len(seen) - 1]
        return text, {"prompt_tokens": 10, "completion_tokens": 5}

    return call, seen


def reply(text, finish="stop", usage=None):
    return {"choices": [{"message": {"content": text}, "finish_reason": finish}],
            "usage": usage or {"prompt_tokens": 7, "completion_tokens": 3}}


def test_three_stages_run_in_order_and_feed_forward():
    call, seen = fake_call(["PLAN-1", "ATTACK-2", "FINAL-3"])
    record = consilium.run_consilium("Q?", call, "vendor/a", "vendor/b", max_tokens=500)
    assert [s["model"] for s in seen] == ["vendor/a", "vendor/b", "vendor/a"]
    assert [s["stage"] for s in record["stages"]] == ["proposal", "review", "synthesis"]
    assert "PLAN-1" in seen[1]["messages"][1]["content"]
    assert "PLAN-1" in seen[2]["messages"][1]["content"] and "ATTACK-2" in seen[2]["messages"][1]["content"]
    assert record["stages"][-1]["text"] == "FINAL-3"
    assert all(s["max_tokens"] == 500 for s in seen)


def test_tokens_and_seconds_are_reported():
    call, _ = fake_call(["a", "b", "c"])
    record = consilium.run_consilium("Q?", call, "m/a", "m/b")
    assert record["tokens"] == {"prompt_tokens": 30, "completion_tokens": 15}
    assert record["seconds"] >= 0


def test_truncated_reply_is_retried_with_a_doubled_limit():
    calls = []

    def transport(url, body, headers, timeout):
        calls.append(json.loads(body)["max_tokens"])
        if len(calls) == 1:
            return reply("half an answer", finish="length")
        return reply("complete answer")

    text, usage = consilium.chat("https://example.test/v1", "k", "m", [{"role": "user", "content": "x"}],
                                max_tokens=100, transport=transport, sleep=NO_SLEEP)
    assert text == "complete answer"
    assert calls == [100, 200]
    # the truncated attempt was really billed, so the retry adds up rather than replacing it
    assert usage["prompt_tokens"] == 14


def test_unfixable_truncation_is_marked_not_silent():
    def transport(url, body, headers, timeout):
        return reply("cut off here", finish="length")

    text, _ = consilium.chat("https://example.test/v1", "k", "m", [{"role": "user", "content": "x"}],
                             max_tokens=50, transport=transport, sleep=NO_SLEEP, retries=2)
    assert text.startswith("cut off here") and "truncated by the token limit" in text


def test_reasoning_field_is_used_when_content_is_empty():
    def transport(url, body, headers, timeout):
        return {"choices": [{"message": {"content": "", "reasoning": "thought it through"},
                             "finish_reason": "stop"}], "usage": {}}

    text, _ = consilium.chat("https://example.test/v1", "k", "m", [{"role": "user", "content": "x"}],
                             transport=transport, sleep=NO_SLEEP)
    assert text == "thought it through"


def test_empty_responses_end_in_a_clear_error():
    def transport(url, body, headers, timeout):
        return {"choices": [{"message": {"content": ""}, "finish_reason": "stop"}]}

    try:
        consilium.chat("https://example.test/v1", "k", "m", [{"role": "user", "content": "x"}],
                       transport=transport, sleep=NO_SLEEP, retries=2)
    except RuntimeError as exc:
        assert "no usable reply" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")


def test_transport_errors_are_retried_then_raised():
    calls = []

    def transport(url, body, headers, timeout):
        calls.append(1)
        raise urllib.error.URLError("connection reset")

    try:
        consilium.chat("https://example.test/v1", "k", "m", [{"role": "user", "content": "x"}],
                       transport=transport, sleep=NO_SLEEP, retries=3)
    except RuntimeError as exc:
        assert "connection reset" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")
    assert len(calls) == 3


def test_error_payload_from_the_provider_is_reported():
    def transport(url, body, headers, timeout):
        return {"error": {"message": "model not found"}}

    try:
        consilium.chat("https://example.test/v1", "k", "m", [{"role": "user", "content": "x"}],
                       transport=transport, sleep=NO_SLEEP, retries=1)
    except RuntimeError as exc:
        assert "model not found" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")


def test_render_has_all_three_sections_and_the_question():
    call, _ = fake_call(["PLAN", "ATTACK", "FINAL"])
    text = consilium.render(consilium.run_consilium("Should we shard?", call, "m/a", "m/b"))
    assert "Should we shard?" in text
    for marker in ("1. Plan (author)", "2. Attack (reviewer)", "3. Final plan"):
        assert marker in text
    assert "m/a" in text and "m/b" in text


def test_slug_is_filesystem_safe():
    assert consilium.slug("Move the mail server?! 2026") == "Move-the-mail-server-2026"
    assert consilium.slug("№§") == "question"


def test_main_writes_the_transcript(tmp_path, monkeypatch):
    out = tmp_path / "out"
    monkeypatch.setenv("CONSILIUM_TEST_KEY", "secret-not-real")
    answers = iter(["PLAN", "ATTACK", "FINAL"])
    monkeypatch.setattr(consilium, "chat",
                        lambda *a, **kw: (next(answers), {"prompt_tokens": 1, "completion_tokens": 1}))
    code = consilium.main(["--question", "Is the tunnel enough?", "--model-a", "m/a",
                           "--model-b", "m/b", "--api-key-env", "CONSILIUM_TEST_KEY",
                           "--out-dir", str(out)])
    assert code == 0
    files = list(out.glob("*.md"))
    assert len(files) == 1
    body = files[0].read_text(encoding="utf-8")
    assert "Is the tunnel enough?" in body and "FINAL" in body


def test_main_requires_models_and_key(tmp_path, monkeypatch):
    monkeypatch.setenv("CONSILIUM_TEST_KEY", "secret-not-real")
    for argv in ([ "--question", "q", "--model-b", "m/b", "--api-key-env", "CONSILIUM_TEST_KEY",
                   "--out-dir", str(tmp_path)],
                 ["--question", "q", "--model-a", "m/a", "--api-key-env", "CONSILIUM_TEST_KEY",
                  "--out-dir", str(tmp_path)]):
        try:
            consilium.main(argv)
        except SystemExit as exc:
            assert "required" in str(exc)
        else:
            raise AssertionError("expected SystemExit")
    monkeypatch.delenv("CONSILIUM_TEST_KEY")
    try:
        consilium.main(["--question", "q", "--model-a", "m/a", "--model-b", "m/b",
                        "--api-key-env", "CONSILIUM_TEST_KEY", "--out-dir", str(tmp_path)])
    except SystemExit as exc:
        assert "is not set" in str(exc)
    else:
        raise AssertionError("expected SystemExit")


if __name__ == "__main__":
    import tempfile
    import traceback

    class _MP:
        def __init__(self):
            self._undo = []

        def setenv(self, k, v):
            import os
            self._undo.append((k, os.environ.get(k)))
            os.environ[k] = v

        def delenv(self, k):
            import os
            self._undo.append((k, os.environ.get(k)))
            os.environ.pop(k, None)

        def setattr(self, obj, name, value):
            self._undo.append((obj, name, getattr(obj, name)))
            setattr(obj, name, value)

        def undo(self):
            import os
            for item in reversed(self._undo):
                if len(item) == 2 and isinstance(item[0], str):
                    os.environ[item[0]] = item[1] if item[1] is not None else os.environ.pop(item[0], None)
                elif len(item) == 3:
                    setattr(item[0], item[1], item[2])

    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        mp = _MP()
        try:
            if "tmp_path" in fn.__code__.co_varnames[:fn.__code__.co_argcount]:
                with tempfile.TemporaryDirectory() as tmp:
                    fn(pathlib.Path(tmp), mp)
            else:
                fn()
            print(f"ok   {name}")
        except Exception:
            failed += 1
            print(f"FAIL {name}")
            traceback.print_exc()
        finally:
            mp.undo()
    print(f"{len(tests) - failed}/{len(tests)} passed")
    raise SystemExit(1 if failed else 0)
