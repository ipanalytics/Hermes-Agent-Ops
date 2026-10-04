#!/usr/bin/env python3
"""Offline tests for autocompact.py — no Hermes host, no network, no database.

Run either way:
    python3 tests/test_state_sections.py
    pytest tests/test_state_sections.py

The engine runs inside the Hermes agent runtime, so the test first installs
lightweight stubs for the four runtime modules it imports (the elide marker,
the context-engine base class, the token estimate, the auxiliary model call)
and then exercises the parts that decide what survives a compaction:

  * section parsing and rendering (the block is machine-read on the next cycle);
  * carry-over of the previous block without asking the model to re-summarise;
  * the exact-value window and its eviction order;
  * the invariants `compress()` promises the host: a no-op returns the very
    same list object, one compaction leaves exactly one state block, and no
    tool call is left without its result.
"""
import importlib.util
import json
import os
import pathlib
import sys
import tempfile
import types

MODULE = pathlib.Path(__file__).resolve().parents[1] / "autocompact.py"

# Рабочие каталоги — во временную папку: тест не должен читать чужой config.yaml
# и не должен писать в живой журнал движка.
_TMP = tempfile.mkdtemp(prefix="autocompact-test-")
os.environ["HERMES_HOME"] = _TMP
os.environ["AUTOCOMPACT_JOURNAL"] = "off"


class _Resp:
    def __init__(self, payload):
        self.content = json.dumps(payload, ensure_ascii=False)


def _state_payload():
    return {
        "task": "Переписать движок сжатия",
        "decisions": ["Сжимаем на границе задачи, а не только у стенки"],
        "constraints": ["Пары tool_call и результат не разрывать"],
        "identifiers": ["путь: /etc/nginx/nginx.conf"],
        "done": ["Прочитан старый движок"],
        "open": ["Прогнать тест продолжения"],
        "next": ["Запустить resume_eval.py"],
        "verify": ["Перечитать хвост"],
    }


def load_engine(call_llm=None):
    """Импорт движка со стабами рантайма Hermes."""
    agent = types.ModuleType("agent")
    marker = types.ModuleType("agent.compression_marker")
    marker.elide = lambda text, limit, *a, **kw: (text[:limit] + " …") if len(text) > limit else text
    meta = types.ModuleType("agent.model_metadata")
    meta.estimate_messages_tokens_rough = lambda msgs: sum(
        len(str(m.get("content") or "")) for m in msgs) // 4

    engine_base = types.ModuleType("agent.context_engine")

    class ContextEngine:  # минимальный контракт хоста
        def __init__(self):
            pass

    engine_base.ContextEngine = ContextEngine

    def _default_call(**kw):
        return _Resp(_state_payload())

    aux = types.ModuleType("agent.auxiliary_client")
    aux.call_llm = call_llm or _default_call
    aux.extract_content_or_reasoning = lambda resp: getattr(resp, "content", "") or ""

    sys.modules.update({
        "agent": agent, "agent.compression_marker": marker, "agent.model_metadata": meta,
        "agent.context_engine": engine_base, "agent.auxiliary_client": aux,
    })
    spec = importlib.util.spec_from_file_location("autocompact_under_test", MODULE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def transcript(pairs=12, big="x" * 9000):
    """Синтетическая история: тяжёлая середина и мелкий хвост (иначе хвост съедает всё)."""
    msgs = [
        {"role": "system", "content": "Ты Hermes."},
        {"role": "system", "content": "Память: ..."},
        {"role": "user", "content": "Почини движок сжатия, файл /etc/nginx/nginx.conf"},
        {"role": "assistant", "content": "Смотрю конфиг."},
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "c1", "type": "function",
             "function": {"name": "read_file", "arguments": '{"path": "/etc/nginx/nginx.conf"}'}}]},
        {"role": "tool", "tool_call_id": "c1", "tool_name": "read_file", "content": big},
        {"role": "assistant", "content": "Порог 250000, движок старый."},
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "c2", "type": "function",
             "function": {"name": "terminal", "arguments": '{"command": "systemctl status nginx.service"}'}}]},
        {"role": "tool", "tool_call_id": "c2", "tool_name": "terminal", "content": big},
        {"role": "assistant", "content": "Ошибка: HTTP 400 max_tokens_exceeded."},
    ]
    for i in range(pairs):
        msgs.append({"role": "user", "content": f"шаг {i}: продолжаю"})
        msgs.append({"role": "assistant", "content": f"шаг {i}: сделано"})
    return msgs


# --- секции, разбор, рендер -----------------------------------------------------------

def test_limit_by_chars_keeps_prefix():
    mod = load_engine()
    assert mod._limit_by_chars(["aaa", "bbb", "ccc"], 100) == ["aaa", "bbb", "ccc"]
    assert mod._limit_by_chars(["aaa", "bbb", "ccc"], 10) == ["aaa"]
    assert mod._limit_by_chars(["aaa", "bbb", "ccc"], 12) == ["aaa", "bbb"]


def test_parse_sections_roundtrip():
    mod = load_engine()
    eng = mod.AutoCompactEngine()
    state = _state_payload()
    text = eng._render_state(state, 10, 4000, "моделью сжатия")
    back = mod._parse_sections(text)
    assert back["task"] == ["Переписать движок сжатия"], back
    assert back["decisions"] == state["decisions"], back
    assert back["identifiers"] == state["identifiers"], back
    assert back["next"] == state["next"], back
    assert mod.STATE_HEADER in text and mod.STATE_FOOTER in text


def test_render_keeps_both_ends_and_marks_the_cut():
    mod = load_engine()
    eng = mod.AutoCompactEngine()
    items = [f"путь: /srv/data/file_{i:03d}.conf" for i in range(800)]
    text = eng._render_state({"identifiers": items}, 5, 100, "моделью сжатия")
    parsed = mod._parse_sections(text)["identifiers"]
    assert parsed[0] == items[0], "свежий/перенесённый край (голова списка) обязан выжить"
    assert parsed[-1] == items[-1], "хвост списка (самое новое из собранного) обязан выжить"
    assert len(parsed) < len(items), "середина должна быть вырезана"
    assert any("середина списка вырезана" in line for line in parsed), parsed[:3]


# --- перенос прошлого блока -----------------------------------------------------------

def test_merge_fresh_wins_and_dedupes():
    mod = load_engine()
    prev = {"decisions": ["Держим порог 250000", "Старое решение"], "task": "Старая задача"}
    new = {"decisions": ["держим ПОРОГ   250000"], "task": "Новая задача"}
    merged = mod._merge_state(prev, new)
    assert merged["task"] == "Новая задача"
    assert merged["decisions"][0] == "держим ПОРОГ   250000"
    assert "Старое решение" in merged["decisions"]


def test_merge_keeps_prev_task_and_next_when_fresh_empty():
    mod = load_engine()
    prev = {"task": "Старая задача", "next": ["перечитать хвост"]}
    merged = mod._merge_state(prev, {"task": "   ", "next": []})
    assert merged["task"] == "Старая задача"
    assert merged["next"] == ["перечитать хвост"]


def test_identifiers_are_an_eviction_window():
    mod = load_engine()
    fresh = ["путь: /srv/new/a.conf", "путь: /srv/new/b.conf"]
    carried = [f"путь: /srv/old/{i:03d}.conf" for i in range(800)]
    merged = mod._merge_state({"identifiers": carried}, {"identifiers": fresh})
    got = merged["identifiers"]
    assert got[0] == fresh[0] and got[1] == fresh[1], "свежее — сверху"
    assert carried[0] in got, "перенесённое идёт следом за свежим"
    assert carried[600] not in got, "старое вытесняется первым"
    assert sum(len(x) + 3 for x in got) <= 14_000 + 60


# --- точные значения ------------------------------------------------------------------

def test_collect_values_reads_tool_call_arguments():
    mod = load_engine()
    msgs = [{"role": "assistant", "content": "", "tool_calls": [
        {"id": "c9", "type": "function", "function": {
            "name": "terminal", "arguments": '{"command": "systemctl restart nginx.service"}'}}]}]
    found = dict((v, l) for l, v in mod._collect_values(msgs, 20))
    assert any(v.endswith("nginx.service") for v in found), found


def test_ensure_values_adds_missing_fresh_values_verbatim():
    mod = load_engine()
    eng = mod.AutoCompactEngine()
    middle = [{"role": "tool", "tool_call_id": "c1", "tool_name": "read_file",
               "content": "конфиг лежит в /etc/systemd/system/agent-gateway.service и всё"}]
    state = eng._ensure_values({"task": "t", "identifiers": []}, middle)
    assert any("/etc/systemd/system/agent-gateway.service" in x for x in state["identifiers"]), state


# --- блок состояния и приёмочные инварианты -------------------------------------------

def test_state_message_is_marked_and_role_safe():
    mod = load_engine()
    eng = mod.AutoCompactEngine()
    msgs = [{"role": "user", "content": "u"}, {"role": "user", "content": "u2"},
            {"role": "user", "content": "u3"}]
    block = eng._state_message("текст", 2, msgs, 2)
    assert block[mod.STATE_MARK] is True
    assert block["role"] == "assistant", "два хода одного автора подряд не ставим"


def test_compress_noop_returns_the_same_object():
    mod = load_engine()
    eng = mod.AutoCompactEngine()
    small = [{"role": "system", "content": "s"}, {"role": "user", "content": "коротко"}]
    assert eng.compress(small) is small, "нечего сжимать — хост ждёт тот же самый объект"


def test_compress_leaves_one_block_and_no_orphans():
    mod = load_engine()
    eng = mod.AutoCompactEngine()
    eng.threshold_tokens = 1000
    eng._tail_tokens = 200
    msgs = transcript()
    out = eng.compress(msgs)

    assert out is not msgs
    assert sum(1 for m in out if m.get(mod.STATE_MARK)) == 1, "ровно один блок состояния"
    calls = {str(c.get("id")) for m in out for c in (m.get("tool_calls") or [])}
    results = {str(m.get("tool_call_id")) for m in out if m.get("role") == "tool"}
    assert calls == results, (calls, results)
    assert out[0]["content"] == msgs[0]["content"], "голова неприкосновенна"
    assert out[-1]["content"] == msgs[-1]["content"], "хвост неприкосновенен"
    assert len(out) < len(msgs)

    # второй цикл: работа продолжилась, блок должен переплавиться, а не встать вторым
    grown = out + [
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "c7", "type": "function",
             "function": {"name": "terminal", "arguments": '{"command": "cat /etc/os-release"}'}}]},
        {"role": "tool", "tool_call_id": "c7", "tool_name": "terminal", "content": "y" * 9000},
    ] + [m for i in range(10) for m in ({"role": "user", "content": f"ещё шаг {i}"},
                                        {"role": "assistant", "content": f"ещё готово {i}"})]
    out2 = eng.compress(grown)
    assert sum(1 for m in out2 if m.get(mod.STATE_MARK)) <= 1, "блоки не складываются штабелем"
    assert eng.last_run["prev_block_chars"] > 0, "прошлый блок найден и разобран для переноса"


def test_compress_survives_model_failure():
    def boom(**kw):
        raise RuntimeError("нет связи")

    mod = load_engine(call_llm=boom)
    eng = mod.AutoCompactEngine()
    eng.threshold_tokens = 1000
    eng._tail_tokens = 200
    out = eng.compress(transcript())
    assert sum(1 for m in out if m.get(mod.STATE_MARK)) == 1, "детерминированный путь тоже даёт блок"
    assert eng.last_run["state_src"] == "детерминированно"


def main():
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"ok   {name}")
        except AssertionError as exc:
            failed += 1
            print(f"FAIL {name}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"ERR  {name}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - failed}/{len(tests)} тестов прошло")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
