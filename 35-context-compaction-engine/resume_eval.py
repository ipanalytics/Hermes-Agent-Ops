#!/usr/bin/env python3
"""Приёмка сжатия контекста «по успеху задачи, а не по объёму».

Сжатие считается удачным не тогда, когда много освободило, а тогда, когда агент
ПОСЛЕ сжатия может продолжать работу. Проверяем тремя мерками:

  A. Точные значения. Из середины транскрипта (то, что сжатие вырезает)
     механически вынимаются незаменимые значения — инфраструктурные пути, id
     сессий, хеши, адреса, имена юнитов и файлов, команды, числа с единицами.
     Мусор из веб-выдачи (URL поиска) отбрасывается: продолжению задачи он не
     нужен. Отдельно считаются СВЕЖИЕ значения (последние 15% середины) — по ним
     агент работает сейчас, они и есть «успех продолжения».
  B. Жизнь сессии и анти-храповина: цикл 1 сжимает первую половину истории,
     потом «приходит» вторая половина (работа продолжалась) и срабатывает цикл 2.
     Смотрим, что освобождение и выживание значений не падают, и что в контексте
     остаётся РОВНО ОДИН блок состояния (блоки не складываются штабелем).
  C. Живой опрос (--live): модель составляет вопросы по вырезанной середине с
     золотыми ответами, свежая сессия отвечает, видя ТОЛЬКО сжатый контекст,
     третья судит по золоту.

Запуск — ТОЛЬКО штатным рантаймом Hermes (hermes_bootstrap ставит окружение):

    cp ~/.hermes/state.db /tmp/state_copy.db          # живая база не читается
    PY=$(ls -d ~/.hermes/tools/python-*/bin/python3 | head -1)
    HERMES_HOME="$HOME/.hermes" "$PY" -I resume_eval.py \
      --db /tmp/state_copy.db --session <session_id> --cycles 2 --live

Отчёт: JSON + markdown в --out (по умолчанию ~/.hermes/data/compaction_resume_eval/<ts>/).
Живой журнал движка не трогается (AUTOCOMPACT_JOURNAL=off).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import time
from typing import Any, Dict, List, Tuple

HERMES_HOME = os.path.realpath(os.environ.get("HERMES_HOME") or os.path.expanduser("~/.hermes"))
REPO = os.path.join(HERMES_HOME, "hermes-agent")
if REPO not in sys.path:
    sys.path.insert(0, REPO)
os.environ["HERMES_HOME"] = HERMES_HOME
os.environ.setdefault("AUTOCOMPACT_JOURNAL", "off")  # стенд: свой отчёт

import hermes_bootstrap  # noqa: E402,F401  (ставит sys.path активного окружения)

LIVE_DB = os.path.join(HERMES_HOME, "state.db")
FRESH_SHARE = 0.15          # «свежая» часть середины — работа последних ходов

FACT_PATTERNS: List[Tuple[str, str]] = [
    ("infra_path", r"/(?:home|var|etc|opt|usr|tmp|srv|mnt|run|root|proc)(?:/[\w.@+=:-]{1,}){1,}/?"),
    ("session", r"\b\d{8}_\d{6}_[0-9a-f]{8}\b"),
    ("hash", r"\b[0-9a-f]{8,64}\b"),
    ("ip", r"\b\d{1,3}(?:\.\d{1,3}){3}\b"),
    ("unit", r"\b[\w-]+\.(?:service|timer|py|json|jsonl|db|yaml|yml|md|sh|conf)\b"),
    ("num", r"\b\d[\d.,]*\s?(?:GB|MB|KB|kB|токен\w*|знак\w*|сек|мин|ч|€|\$)\b"),
    ("cmd", r"`[^`\n]{5,90}`"),
]
PER_TYPE_CAP = 80

# Веб-мусор: ссылки из выдачи поиска. Продолжению задачи не нужны — их отсутствие
# в блоке состояния не потеря.
NOISE_TOKENS = ("http", "://", "www.", ".com", ".net", ".org", ".io/", ".dev/", ".ru/",
                ".de/", ".ai/", ".app", "github.com", "stackoverflow", "netlify",
                "youtube", "reddit", "wikipedia", "docs.", "/guide/", "/blog/")


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def is_noise(val: str) -> bool:
    low = val.lower()
    return any(tok in low for tok in NOISE_TOKENS)


def load_messages(db: str, session_id: str, limit: int = 4000) -> List[Dict[str, Any]]:
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        rows = con.execute(
            "select role, content, tool_call_id, tool_calls, tool_name from messages "
            "where session_id=? order by id", (session_id,)).fetchall()
    finally:
        con.close()
    if limit and len(rows) > limit:
        rows = rows[-limit:]
    msgs: List[Dict[str, Any]] = []
    for role, content, tcid, tcalls, tname in rows:
        m: Dict[str, Any] = {"role": role, "content": content or ""}
        if tcid:
            m["tool_call_id"] = tcid
        if tname:
            m["tool_name"] = tname
        if tcalls:
            try:
                m["tool_calls"] = json.loads(tcalls)
            except Exception:  # noqa: BLE001
                pass
        msgs.append(m)
    return msgs


def _collect(messages: List[Dict[str, Any]], cap: int = PER_TYPE_CAP) -> Dict[str, List[str]]:
    facts: Dict[str, List[str]] = {}
    for name, pattern in FACT_PATTERNS:
        rx = re.compile(pattern)
        seen: List[str] = []
        for msg in messages:
            if len(seen) >= cap:
                break
            for raw in rx.findall(str(msg.get("content") or "")):
                val = norm(raw).strip("`").rstrip(":;,.")
                if len(val) < 4 or val in seen or is_noise(val):
                    continue
                if val.startswith(("/proc/", "/dev/")):
                    continue
                seen.append(val)
                if len(seen) >= cap:
                    break
        # обрезанные дубликаты не считаем отдельными значениями
        facts[name] = [v for v in seen if not any(o != v and o.startswith(v + "/") for o in seen)]
    return facts


def _msg_chars(msg: Dict[str, Any]) -> int:
    n = len(str(msg.get("content") or ""))
    if msg.get("tool_calls"):
        try:
            n += len(json.dumps(msg["tool_calls"], ensure_ascii=False))
        except Exception:  # noqa: BLE001
            pass
    return n


def extract_facts(middle: List[Dict[str, Any]], window_chars: int = 72_000
                  ) -> Dict[str, Dict[str, List[str]]]:
    """Значения, которые обязаны пережить сжатие. Отдельно — СВЕЖИЕ: ровно то окно в конце
    вырезанной части, которое читает модель состояния (контракт движка: свежий край — точно,
    остальное достаётся через session_search). Набор «всех» берём по третям, чтобы не
    скатиться в один угол."""
    if len(middle) < 3:
        return {"all": _collect(middle), "fresh": _collect(middle)}
    third = max(1, len(middle) // 3)
    spread = middle[:third] + middle[third:2 * third] + middle[2 * third:]
    used, fresh = 0, []
    for msg in reversed(middle):
        fresh.append(msg)
        used += _msg_chars(msg)
        if used >= window_chars:
            break
    return {"all": _collect(spread), "fresh": _collect(fresh[::-1])}


def text_of(messages: List[Dict[str, Any]]) -> str:
    parts = []
    for m in messages:
        parts.append(str(m.get("content") or ""))
        if m.get("tool_calls"):
            try:
                parts.append(json.dumps(m["tool_calls"], ensure_ascii=False))
            except Exception:  # noqa: BLE001
                pass
    return norm("\n".join(parts))


def survival(facts: Dict[str, List[str]], text: str, sample: int = 12) -> Dict[str, Any]:
    low = text.lower()
    per_type: Dict[str, Any] = {}
    total = kept = 0
    missing: List[str] = []
    for name, values in facts.items():
        ok = 0
        for val in values:
            hit = norm(val) in text or norm(val).lower() in low
            ok += 1 if hit else 0
            if not hit and len(missing) < sample:
                missing.append(f"{name}:{val[:70]}")
        per_type[name] = {"kept": ok, "of": len(values),
                          "pct": round(100 * ok / len(values), 1) if values else None}
        total += len(values)
        kept += ok
    return {"per_type": per_type, "kept": kept, "of": total,
            "pct": round(100 * kept / total, 1) if total else None, "missing": missing}


def json_from(text: str) -> Any:
    text = str(text or "")
    for opener, closer in (("{", "}"), ("[", "]")):
        i, j = text.find(opener), text.rfind(closer)
        if i >= 0 and j > i:
            try:
                return json.loads(text[i:j + 1])
            except Exception:  # noqa: BLE001
                continue
    return None


def aux(messages: List[Dict[str, Any]], max_tokens: int = 1200, timeout: float = 180.0) -> str:
    from agent.auxiliary_client import call_llm, extract_content_or_reasoning
    resp = call_llm(task="compression", messages=messages, temperature=0.0,
                    max_tokens=max_tokens, timeout=timeout)
    try:
        return str(extract_content_or_reasoning(resp) or "")
    except Exception:  # noqa: BLE001
        return str(getattr(resp, "content", "") or "")


def build_questions(middle_text: str, n: int) -> List[Dict[str, str]]:
    prompt = (
        f"Ниже фрагмент рабочей переписки инженера и агента. Составь {n} вопросов, ответы на которые "
        "нужны, чтобы продолжить эту работу: конкретные значения (пути, id, имена файлов и юнитов, "
        "адреса, команды, числа), принятые решения и незакрытые пункты. Ответ на каждый вопрос — короткая "
        "точная строка ИЗ ТЕКСТА (дословно, без домыслов). Вопрос должен быть осмысленным для того, кто "
        "текста не видел.\n\n"
        'Ответ строго JSON: [{"q": "...", "a": "..."}, ...]\n\n'
        "ТЕКСТ:\n" + middle_text[:60000]
    )
    data = json_from(aux([{"role": "user", "content": prompt}], max_tokens=1600))
    out: List[Dict[str, str]] = []
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and item.get("q") and item.get("a"):
                out.append({"q": str(item["q"]).strip(), "a": str(item["a"]).strip()})
    return out[:n]


def answer_and_judge(questions: List[Dict[str, str]], context_text: str) -> Dict[str, Any]:
    rows = []
    for item in questions:
        try:
            pred = aux([{"role": "user", "content": (
                "Ты продолжаешь работу по контексту ниже. Ответь на вопрос ТОЛЬКО по контексту; "
                "если значения нет — напиши «нет в контексте».\n\n"
                f"КОНТЕКСТ:\n{context_text[:60000]}\n\nВОПРОС: {item['q']}")}], max_tokens=400)
        except Exception as exc:  # noqa: BLE001
            pred = f"ОШИБКА: {exc}"
        try:
            verdict_raw = aux([{"role": "user", "content": (
                "Сравни ответ с эталоном. «ВЕРНО» — если ответ передаёт тот же факт (допустимы "
                "перестановки слов), «НЕВЕРНО» — если факта нет, он искажён или ответ «нет в контексте». "
                "Ответь одним словом.\n\n"
                f"ЭТАЛОН: {item['a']}\nОТВЕТ: {pred}")}], max_tokens=20)
        except Exception as exc:  # noqa: BLE001
            verdict_raw = f"ОШИБКА {exc}"
        rows.append({"q": item["q"], "gold": item["a"], "pred": pred.strip()[:400],
                     "verdict": "верно" if "ВЕРНО" in str(verdict_raw).upper() else "неверно"})
    ok = sum(1 for r in rows if r["verdict"] == "верно")
    return {"rows": rows, "correct": ok, "of": len(rows),
            "pct": round(100 * ok / len(rows), 1) if rows else None}


def engine_for(name: str | None):
    import hermes_yaml as yaml
    from agent.agent_init import _select_context_engine
    with open(os.path.join(os.environ["HERMES_HOME"], "config.yaml"), encoding="utf-8") as fh:
        cfg = yaml.YAML(typ="safe").load(fh)
    if name:
        cfg = dict(cfg)
        cfg["context"] = {**(cfg.get("context") or {}), "engine": name}
    eng = _select_context_engine(cfg)
    if eng is None:
        raise SystemExit("движок не выбран (встроенный compressor этим стендом не тестируется)")
    return eng


def structure(out: List[Dict[str, Any]]) -> Dict[str, Any]:
    blocks = [m for m in out if m.get("_autocompact_state")]
    calls, results = set(), set()
    for m in out:
        for c in (m.get("tool_calls") or []):
            cid = c.get("id") or ((c.get("function") or {}).get("name"))
            if cid:
                calls.add(cid)
        if m.get("tool_call_id"):
            results.add(str(m["tool_call_id"]))
    return {"state_blocks": len(blocks), "orphan_results": len(results - calls),
            "calls_without_result": len(calls - results)}


def main() -> int:
    ap = argparse.ArgumentParser(description="Приёмка сжатия по продолжению задачи")
    ap.add_argument("--db", required=True, help="КОПИЯ state.db (живую не читаю)")
    ap.add_argument("--session", required=True)
    ap.add_argument("--engine", default=None, help="context.engine (по умолчанию — из config.yaml)")
    ap.add_argument("--cycles", type=int, default=2,
                    help="1 = один проход; 2 = плюс вторая половина истории и повторное сжатие")
    ap.add_argument("--live", action="store_true", help="живой опрос модели (деньги/время)")
    ap.add_argument("--questions", type=int, default=8)
    ap.add_argument("--limit", type=int, default=4000, help="взять последние N сообщений сессии")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    if os.path.realpath(os.path.expanduser(args.db)) == LIVE_DB:
        raise SystemExit("это живая state.db — сначала скопируй: cp ~/.hermes/state.db /tmp/state_copy.db")

    from agent.model_metadata import estimate_messages_tokens_rough as est

    msgs = load_messages(args.db, args.session, args.limit)
    if len(msgs) < 20:
        raise SystemExit(f"в сессии {args.session} всего {len(msgs)} сообщений — нечего сжимать")

    eng = engine_for(args.engine)
    head_end, tail_start = eng._bounds(msgs)
    middle = msgs[head_end:tail_start]
    mod = next((m for name, m in sys.modules.items()
                if name.endswith(".autocompact") and hasattr(m, "TRANSCRIPT_CHARS")), None)
    window_chars = int(getattr(mod, "TRANSCRIPT_CHARS", 72_000))
    facts = extract_facts(middle, window_chars)
    n_all = sum(len(v) for v in facts["all"].values())

    hard_cut = msgs[:head_end] + msgs[tail_start:]     # нижняя граница: обрез без блока
    base = survival(facts["all"], text_of(hard_cut))

    report: Dict[str, Any] = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "session": args.session, "engine": eng.name,
        "messages_in": len(msgs), "tokens_in": est(msgs), "middle_messages": len(middle),
        "facts_all": n_all,
        "facts_by_type": {k: len(v) for k, v in facts["all"].items()},
        "hard_cut_baseline": {"tokens": est(hard_cut), "survival_pct": base["pct"]},
        "cycles": [],
    }
    print(f"движок: {eng.name} | сообщений {len(msgs)} | токенов {est(msgs)} | "
          f"вырезанная часть {len(middle)} сообщений | значений в ней {n_all}")
    print(f"нижняя граница — обрез без блока состояния: выжило {base['pct']}% значений, токенов {est(hard_cut)}")

    questions: List[Dict[str, str]] = []
    rest: List[Dict[str, Any]] = []
    current = msgs
    if args.cycles > 1:
        half = len(msgs) // 2
        current, rest = msgs[:half], msgs[half:]   # цикл 1 видит первую половину, дальше «приходит» вторая

    carry_gold: Dict[str, List[str]] = {}
    for cycle in range(1, args.cycles + 1):
        # Свежие значения считаем от ОКНА ЭТОГО цикла, а не от всей истории: цикл 1 видит только
        # первую половину, и требовать с него факты второй половины бессмысленно.
        he, ts = eng._bounds(current)
        fresh_gold = extract_facts(current[he:ts], window_chars)["fresh"]
        before, ctx_before = est(current), text_of(current)
        if args.live and not questions:
            questions = build_questions(ctx_before, args.questions)
        out = eng.compress(current, current_tokens=before)
        after = est(out)
        if out is current or after >= before:
            print(f"цикл {cycle}: сжатия не вышло ({before} → {after}) — стоп")
            break
        surv = survival(facts["all"], text_of(out))
        fresh = survival(fresh_gold, text_of(out))
        carry = survival(carry_gold, text_of(out)) if carry_gold else {"pct": None, "missing": []}
        blk = next((m for m in out if m.get("_autocompact_state")), None)
        blk_text = str(blk.get("content") or "") if blk else ""
        carry_block = survival(carry_gold, blk_text) if carry_gold else {"pct": None}
        fresh_block = survival(fresh_gold, blk_text)
        st = structure(out)
        block = blk
        row: Dict[str, Any] = {
            "cycle": cycle, "tokens_before": before, "tokens_after": after,
            "freed_pct": round(100 * (before - after) / before, 1), "messages_after": len(out),
            "survival_pct": surv["pct"], "survival_fresh_pct": fresh["pct"],
            "fresh_of": sum(len(v) for v in fresh_gold.values()), "carry_pct": carry["pct"],
            "carry_block_pct": carry_block["pct"], "fresh_block_pct": fresh_block["pct"],
            "survival_per_type": surv["per_type"], "missing_sample": surv["missing"],
            "state_block_chars": len(block.get("content") or "") if block else 0,
            "state_src": eng.last_run.get("state_src") if eng.last_run else None,
            "prev_block_chars": (eng.last_run or {}).get("prev_block_chars"),
            "ids_in_block": (eng.last_run or {}).get("ids_in_block"), **st}
        if args.live and questions:
            row["live"] = answer_and_judge(questions, text_of(out))
        report["cycles"].append(row)
        print(f"цикл {cycle}: {before} → {after} токенов (освобождено {row['freed_pct']}%), сообщений {len(out)}, "
              f"блок {row['state_block_chars']} знаков ({row['state_src']}), значений в блоке "
              f"{row['ids_in_block']}, прошлый блок найден: {row['prev_block_chars']} знаков, "
              f"блоков в контексте {st['state_blocks']}, сирот {st['orphan_results']}")
        print(f"         выжило значений: свежих {fresh['pct']}% (из {row['fresh_of']}), из них в самом блоке "
              f"{fresh_block['pct']}%, всего по вырезанной части {surv['pct']}%"
              + (f", перенесённых из прошлого цикла {carry['pct']}% (в блоке {carry_block['pct']}%)"
                 if carry["pct"] is not None else ""))
        print("         по типам: " + " ".join(f"{k}={v['pct']}%" for k, v in surv["per_type"].items() if v["of"]))
        if args.live and "live" in row:
            print(f"         живой опрос: {row['live']['correct']}/{row['live']['of']} ({row['live']['pct']}%)")
        if surv["missing"]:
            print(f"         потеряно (примеры): {', '.join(surv['missing'][:5])}")
        carry_gold = fresh_gold
        if rest:
            current = out + rest      # сессия продолжалась: новая работа поверх сжатого контекста
            rest = []
        else:
            current = out

    bars: List[Dict[str, Any]] = []
    c1 = report["cycles"][0] if report["cycles"] else None
    last = report["cycles"][-1] if report["cycles"] else None
    if c1:
        bars.append({"bar": "свежие значения 1-го цикла (окно модели состояния) выжили ≥70%",
                     "value": f"{c1['survival_fresh_pct']}% из {c1['fresh_of']}",
                     "pass": (c1["survival_fresh_pct"] or 0) >= 70})
        bars.append({"bar": "все значения вырезанной части (справочно: старое достаётся через session_search)",
                     "value": c1["survival_pct"], "pass": (c1["survival_pct"] or 0) >= 50, "gate": False})
        bars.append({"bar": "освобождено ≥50%", "value": c1["freed_pct"], "pass": c1["freed_pct"] >= 50})
        bars.append({"bar": "структура цела: блок один, сирот нет",
                     "value": f"блоков {c1['state_blocks']}, сирот {c1['orphan_results']}",
                     "pass": c1["state_blocks"] <= 1 and c1["orphan_results"] == 0})
    if last and c1 and last is not c1:
        bars.append({"bar": "после 2-го сжатия блок по-прежнему один (не штабелем)",
                     "value": f"блоков {last['state_blocks']}, сирот {last['orphan_results']}",
                     "pass": last["state_blocks"] == 1 and last["orphan_results"] == 0})
        bars.append({"bar": "освобождение не упало вдвое во 2-м цикле",
                     "value": f"{c1['freed_pct']}% → {last['freed_pct']}%",
                     "pass": last["freed_pct"] >= 0.5 * c1["freed_pct"]})
        bars.append({"bar": "перенесённые значения (блок 1-го цикла) не потеряны при 2-м сжатии ≥80%",
                     "value": f"{last['carry_pct']}% из {c1['fresh_of']}",
                     "pass": (last["carry_pct"] or 0) >= 80})
        bars.append({"bar": "свежие значения 2-го цикла выжили ≥70%",
                     "value": f"{last['survival_fresh_pct']}% из {last['fresh_of']}",
                     "pass": (last["survival_fresh_pct"] or 0) >= 70})
    if args.live:
        for row in report["cycles"]:
            if "live" in row:
                bars.append({"bar": f"живой опрос после цикла {row['cycle']} ≥75%",
                             "value": row["live"]["pct"], "pass": (row["live"]["pct"] or 0) >= 75})
    for b in bars:
        b.setdefault("gate", True)
    report["bars"] = bars
    gates = [b for b in bars if b["gate"]]
    report["verdict"] = "PASS" if gates and all(b["pass"] for b in gates) else "FAIL"

    out_dir = args.out or os.path.join(os.path.expanduser("~/.hermes/data/compaction_resume_eval"),
                                       time.strftime("%Y%m%d-%H%M%S"))
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    with open(os.path.join(out_dir, "report.md"), "w", encoding="utf-8") as fh:
        fh.write(f"# Приёмка сжатия (продолжение задачи) — {report['verdict']}\n\n")
        fh.write(f"Сессия `{report['session']}`, движок `{report['engine']}`, вход "
                 f"{report['messages_in']} сообщений / {report['tokens_in']} токенов, "
                 f"значений к проверке в вырезанной части {report['facts_all']}.\n\n")
        fh.write(f"Обрез без блока состояния (нижняя граница): "
                 f"{report['hard_cut_baseline']['survival_pct']}% значений.\n\n")
        for row in report["cycles"]:
            fh.write(f"- цикл {row['cycle']}: {row['tokens_before']} → {row['tokens_after']} токенов "
                     f"({row['freed_pct']}%), значений всего {row['survival_pct']}%, свежих "
                     f"{row['survival_fresh_pct']}%, блок {row['state_block_chars']} знаков "
                     f"({row['state_src']}), блоков {row['state_blocks']}\n")
        for b in bars:
            fh.write(f"- [{'✓' if b['pass'] else '✗'}] {b['bar']} — {b['value']}\n")
        if args.live:
            fh.write("\n## Живой опрос\n\n")
            for row in report["cycles"]:
                for r in (row.get("live") or {}).get("rows", []):
                    fh.write(f"- {'✓' if r['verdict'] == 'верно' else '✗'} {r['q']}\n"
                             f"  - эталон: {r['gold']}\n  - ответ: {r['pred']}\n")
    print("\n=== приговор ===")
    for b in bars:
        mark = ("✓" if b["pass"] else "✗") if b["gate"] else "·"
        print(f"[{mark}] {b['bar']} — {b['value']}")
    print(f"ИТОГ: {report['verdict']} | отчёт: {out_dir}/report.json")
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
