"""AutoCompact — движок сжатия контекста Hermes: сжимаем по рабочему состоянию, а не по объёму.

Почему он есть
--------------
Прежний движок вырезал устаревшие результаты инструментов решением дешёвой модели-арбитра, но
текст пользователя и ассистента не сокращал никогда. Недельный замер на рабочем контуре показал,
чем это кончается: «текстовый пол» растёт с каждым циклом
(43K → 139K, 91K → 240K, 175K → 359K токенов), доля освобождаемого падает (89% → 55%, 76% → 20%,
63% → 8%), а одна сессия на 200K-окне встала намертво (0% освобождения). Сжатие выбиралось по
объёму — «перевалило за порог, режем», — и качество сжатия не измерялось вообще.

Что делает этот движок (по мотивам arXiv 2610.02163, AutoCompact)
-----------------------------------------------------------------
1. КОГДА сжимать. Не только у стенки. Сжимаем на границе задачи: пользователь заговорил снова,
   а контекст уже больше ~60% порога — значит предыдущий заход исследования закончен и устарел
   (`should_compress_preflight`). Порог как жёсткий предохранитель остаётся (`should_compress`).
2. ЧТО сохранять. Вместо пересказа процесса — рабочее состояние: задача, решения и ограничения,
   ТОЧНЫЕ значения дословно (пути, id, ключи, команды, тексты ошибок, числа), сделанное, открытое,
   следующий шаг и что перепроверить после сжатия. Пишет дешёвая aux-модель сжатия
   (`auxiliary.compression`), а не модель-арбитр: та умеет выбирать, но не писать.
3. Как продолжать. Блок состояния встаёт сразу за защищённой головой; последние `protect_last_n`
   сообщений остаются дословно. Блок помечен `_autocompact_state`, поэтому на следующем цикле он
   не вырезается, а переносится в новое состояние разбором секций — «пол» больше не растёт.
4. Чем проверять. Каждое сжатие журналируется (`data/autocompact_decisions.jsonl`), а приёмка —
   тест продолжения (`resume_eval.py`): судить сжатие по тому, доводит ли оно задачу до конца,
   а не по числу сэкономленных токенов.

Страховки
---------
- голова (system + первый пользовательский ход) и хвост неприкосновенны;
- пары tool_call ↔ результат всегда чинятся, сирот не остаётся;
- модель молчит/ошиблась → детерминированное сжатие, ход не ломается;
- если ничего не сжали, возвращаем ТОТ ЖЕ объект списка (хост считает это no-op).
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from agent.compression_marker import elide
from agent.context_engine import ContextEngine
from agent.model_metadata import estimate_messages_tokens_rough

log = logging.getLogger("agent.context_engine.autocompact")

HERMES_HOME = os.path.expanduser("~/.hermes")
CONFIG_PATH = os.path.join(HERMES_HOME, "config.yaml")
DATA_DIR = os.path.join(HERMES_HOME, "data")
DECISIONS = os.path.join(DATA_DIR, "autocompact_decisions.jsonl")

# Заголовок намеренно содержит "CONTEXT COMPACTION": хост и фронтенды узнают по нему сводку
# (title_generator её пропускает, session_persistence не считает обычным ходом).
STATE_HEADER = "[CONTEXT COMPACTION — WORKING STATE, факты ниже]"
STATE_FOOTER = "⟪конец рабочего состояния⟫"
STATE_MARK = "_autocompact_state"

MAX_STATE_CHARS = 28_000     # потолок всего блока состояния (страховка поверх потолков секций)
# Потолки ПО СЕКЦИЯМ: без них обрезка бьёт по концу блока и уносит «Следующий шаг» и
# «Проверить» — то, ради чего блок и пишется. Хвост списка (старое) отсекается первым.
SECTION_CHAR_CAP = {"task": 900, "decisions": 2600, "constraints": 900, "identifiers": 14000,
                    "done": 1800, "open": 1600, "next": 700, "verify": 700}
TRANSCRIPT_CHARS = 72_000    # сколько знаков истории отдаём модели состояния
STATE_TIMEOUT = 60           # модель состояния: не блокируем ход дольше
MODEL_MAX_TOKENS = 1_400
SHED_MIN_RESULT = 900        # результат инструмента короче — не трогаем
SHED_MIN_TEXT = 4_000        # текст короче — не трогаем

STATE_PROMPT = (
    "Ты — движок сжатия рабочего контекста агента-исполнителя. Ниже часть истории работы, которую "
    "сейчас вырежут из контекста. Собери по ней рабочее состояние так, чтобы агент мог продолжить "
    "работу, не перечитывая историю.\n"
    "Правила:\n"
    "- только факты из истории; ничего не выдумывать и не достраивать;\n"
    "- точные значения переносить ДОСЛОВНО: пути, имена файлов, id, ключи конфигов, команды, "
    "номера строк, коды и тексты ошибок, хеши, суммы, даты — без пересказа и без округления;\n"
    "- «решения» — что решили и почему; «ограничения» — что нельзя или не нужно делать;\n"
    "- «следующий шаг» — 1–3 конкретных действия, с чего продолжить работу;\n"
    "- «проверить» — что перечитать или перезапустить после сжатия, чтобы не работать по устаревшему;\n"
    "- чего нет в истории — пустой список, без догадок.\n"
    "Ответ — только JSON, без пояснений и без markdown-обёртки:\n"
    '{"task": "", "decisions": [], "constraints": [], "identifiers": [], "done": [], '
    '"open": [], "next": [], "verify": []}'
)

_PATH_RE = re.compile(r"(?:/[\w.@+-]+){2,}")
_HEX_RE = re.compile(r"\b[0-9a-f]{8,}\b")
_UNIT_RE = re.compile(r"\b[\w-]+\.(?:service|timer|py|json|jsonl|db|yaml|yml|md|sh|conf)\b")
_CMD_RE = re.compile(r"`([^`\n]{5,90})`")
_SECTION_RE = re.compile(r"^## (.+)$", re.M)
_TITLE_TO_KEY = {"Задача": "task", "Решения": "decisions", "Ограничения": "constraints",
                 "Точные значения": "identifiers", "Сделано": "done", "Открыто": "open",
                 "Следующий шаг": "next", "Проверить после сжатия": "verify"}
# Секции, которые переживают следующий цикл: старое дописывается к свежему с потолком на секцию,
# иначе блок либо растёт без предела, либо тонет при переплавке.
CARRY_LIMITS = {"identifiers": 250, "decisions": 35, "done": 35, "open": 22,
                "constraints": 18, "verify": 18}  # по «Точным значениям» режет потолок знаков, не счёт
FRESH_GUARANTEE = 120     # значений из свежей части доносим ДАЖЕ если модель их не назвала
GUARANTEE_CHARS = 10_000  # и на них — свой потолок знаков, чтобы блок не распух
VALUE_ROOTS = ("/home", "/var", "/etc", "/opt", "/usr", "/tmp", "/srv", "/mnt", "/run")


def _norm_line(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def _parse_sections(text: str) -> Dict[str, List[str]]:
    """Разбор текста прошлого блока состояния по секциям (терпимо к пропускам)."""
    out: Dict[str, List[str]] = {}
    current: Optional[str] = None
    for line in str(text or "").splitlines():
        m = _SECTION_RE.match(line)
        if m:
            current = _TITLE_TO_KEY.get(m.group(1).strip())
            continue
        if current and line.startswith("- "):
            item = line[2:].strip()
            if item:
                out.setdefault(current, []).append(item)
    return out


def _limit_by_chars(items: List[str], budget: int) -> List[str]:
    out: List[str] = []
    used = 0
    for item in items:
        if used + len(item) + 3 > budget:
            break
        out.append(item)
        used += len(item) + 3
    return out


def _merge_state(prev: Dict[str, List[str]], new: Dict[str, Any]) -> Dict[str, Any]:
    """Свежее состояние главнее, старое переносится дословно (без пересказа моделью)."""
    merged: Dict[str, Any] = dict(new)
    for key, cap in CARRY_LIMITS.items():
        fresh = new.get(key)
        if isinstance(fresh, str):
            fresh = [fresh]
        fresh_list = [str(x).strip() for x in (fresh or []) if str(x).strip()]
        seen = {_norm_line(x) for x in fresh_list}
        carried: List[str] = []
        for item in prev.get(key, []):
            if _norm_line(item) in seen:
                continue
            seen.add(_norm_line(item))
            carried.append(item)
        if key == "identifiers":
            # Три группы в одной секции, у каждой свой кусок бюджета: свежие от модели,
            # перенесённые из прошлого блока, дальше движок сам добавит гарантированные.
            # «Точные значения» — окно вытеснения (LRU): свежее сверху, перенесённое ниже,
            # самое старое вытесняется первым. Свежие группы за цикл дают ~7 000 знаков, а потолок
            # секции вдвое больше — значит значения прошлого блока переживают следующий цикл целиком.
            merged[key] = _limit_by_chars(_limit_by_chars(fresh_list, 3_000) + carried, 14_000)[:cap]
        else:
            merged[key] = (fresh_list + carried)[:cap]
    for key in ("task", "next"):
        cur = new.get(key)
        cur_empty = not (cur.strip() if isinstance(cur, str) else cur)
        if cur_empty and prev.get(key):
            merged[key] = prev[key]
    return merged


def _collect_values(messages: List[Dict[str, Any]], limit: int) -> List[Tuple[str, str]]:
    """Точные значения дословно, от свежих к старым: (подпись, значение)."""
    found: List[Tuple[str, str]] = []
    seen = set()
    for msg in reversed(messages):
        text = str(msg.get("content") or "")
        if msg.get("tool_calls"):
            try:  # код и команды живут в аргументах вызова, а не в тексте
                text += "\n" + json.dumps(msg["tool_calls"], ensure_ascii=False)
            except Exception:  # noqa: BLE001
                pass
        if not text:
            continue
        candidates: List[Tuple[str, str]] = []
        for p in _PATH_RE.findall(text):
            if (p.startswith(VALUE_ROOTS) and not p.startswith(("/proc", "/dev"))
                    and 6 <= len(p) <= 140):
                candidates.append(("путь", p))
        candidates += [("идентификатор", h) for h in _HEX_RE.findall(text)]
        candidates += [("файл", u) for u in _UNIT_RE.findall(text)]
        candidates += [("команда", c.strip()) for c in _CMD_RE.findall(text)]
        for label, val in candidates:
            if val in seen or len(val) < 4:
                continue
            seen.add(val)
            found.append((label, val))
            if len(found) >= limit or sum(len(v) + 12 for _, v in found) >= GUARANTEE_CHARS:
                return found
    return found


def _cfg() -> Dict[str, Any]:
    try:
        import yaml
        with open(CONFIG_PATH, encoding="utf-8") as fh:
            return (yaml.safe_load(fh) or {}).get("compression") or {}
    except Exception:  # noqa: BLE001
        return {}


def _cfg_num(key: str, default: float) -> float:
    val = _cfg().get(key)
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _text_of(msg: Dict[str, Any], limit: int = 0) -> str:
    content = msg.get("content")
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(str(block.get("text") or ""))
                elif block.get("type") == "tool_result":
                    parts.append(str(block.get("content") or "")[:400])
            else:
                parts.append(str(block))
        content = " ".join(parts)
    text = str(content or "")
    if limit and len(text) > limit:
        return text[:limit] + f" …(+{len(text) - limit} знаков)"
    return text


def _size(msg: Dict[str, Any]) -> int:
    """Размер сообщения «как в проводе»: текст плюс аргументы вызовов (их в тексте нет,
    но модель их читает и они занимают окно)."""
    n = len(str(msg.get("content") or ""))
    calls = msg.get("tool_calls")
    if calls:
        try:
            n += len(json.dumps(calls, ensure_ascii=False))
        except Exception:  # noqa: BLE001
            n += len(str(calls))
    return n


def _calls(msg: Dict[str, Any]) -> List[Dict[str, Any]]:
    calls = msg.get("tool_calls")
    return [c for c in calls if isinstance(c, dict)] if isinstance(calls, list) else []


def _name_args(call: Dict[str, Any], arg_limit: int) -> Tuple[str, str]:
    fn = call.get("function") if isinstance(call.get("function"), dict) else {}
    name = str(call.get("name") or fn.get("name") or "tool")
    args = call.get("arguments") if call.get("arguments") is not None else fn.get("arguments")
    if not isinstance(args, str):
        args = json.dumps(args, ensure_ascii=False) if args is not None else ""
    if arg_limit and len(args) > arg_limit:
        args = args[:arg_limit] + "…"
    return name, args


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    """Достать JSON-объект из ответа модели: стрип фенсов, первый {...} с балансом скобок."""
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z]*\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    start = raw.find("{")
    if start < 0:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(raw)):
        ch = raw[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                candidate = raw[start:i + 1]
                try:
                    parsed = json.loads(candidate)
                except Exception:  # noqa: BLE001
                    return None
                return parsed if isinstance(parsed, dict) else None
    return None


def _repair_pairs(msgs: List[Dict[str, Any]], head_end: int) -> List[Dict[str, Any]]:
    """Снять сирот: результат без вызова и вызов без результата."""
    result_ids = {str(m.get("tool_call_id")) for m in msgs
                  if m.get("role") == "tool" and m.get("tool_call_id")}
    kept_ids: set = set()
    for m in msgs:
        if m.get("role") != "assistant":
            continue
        calls = _calls(m)
        if not calls:
            continue
        kept = [c for c in calls
                if not str(c.get("id") or c.get("call_id") or "")
                or str(c.get("id") or c.get("call_id") or "") in result_ids]
        kept_ids.update(str(c.get("id") or c.get("call_id") or "") for c in kept)
        m["tool_calls"] = kept or None
    out: List[Dict[str, Any]] = []
    for m in msgs:
        if m.get("role") == "tool" and str(m.get("tool_call_id") or "") not in kept_ids:
            continue
        if (m.get("role") == "assistant" and not _calls(m)
                and not str(m.get("content") or "").strip()):
            # Опустевший после снятия вызова ход: в голове помечаем, из хвоста убираем.
            if len(out) <= max(head_end, 1):
                m["content"] = "⟪вызов инструмента снят при сжатии⟫"
            else:
                continue
        out.append(m)
    return out


class AutoCompactEngine(ContextEngine):
    """Сжатие по рабочему состоянию: факты дословно, процесс вырезается."""

    def __init__(self) -> None:
        self.last_prompt_tokens = 0
        self.last_completion_tokens = 0
        self.last_total_tokens = 0
        self.context_length = 0
        self.compression_count = 0
        self.last_run: Dict[str, Any] = {}
        self.protect_first_n = 3
        self.protect_last_n = 6
        self.emit_automatic_compaction_status = False
        self._configured_threshold = int(_cfg_num("threshold_tokens", 250_000)) or None
        self._preflight_ratio = _cfg_num("autocompact_preflight_ratio", 0.6)
        self._target_ratio = _cfg_num("autocompact_target_ratio", 0.45)
        self._tail_tokens = int(_cfg_num("autocompact_tail_tokens", 25_000))
        self.threshold_tokens = self._configured_threshold or 250_000
        log.info("AutoCompact готов: порог %d токенов, упреждающее сжатие от %d, цель %d, хвост %d",
                 self.threshold_tokens, int(self.threshold_tokens * self._preflight_ratio),
                 int(self.threshold_tokens * self._target_ratio), self._tail_tokens)

    @property
    def name(self) -> str:
        return "autocompact"

    # ---- учёт токенов и решение «когда» ------------------------------------------------

    def update_from_response(self, usage: Dict[str, Any]) -> None:
        usage = usage or {}
        self.last_prompt_tokens = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
        self.last_completion_tokens = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
        self.last_total_tokens = int(usage.get("total_tokens")
                                     or (self.last_prompt_tokens + self.last_completion_tokens))
        if not self.context_length:
            self.context_length = int(usage.get("context_length") or 0)

    def update_model(self, model: str, context_length: int, base_url: str = "", api_key: str = "",
                     provider: str = "", api_mode: str = "") -> None:
        """Хост пересчитывает порог от окна модели — наш порог задан конфигом, его и держим."""
        super().update_model(model, context_length, base_url=base_url, api_key=api_key,
                             provider=provider, api_mode=api_mode)
        if self._configured_threshold:
            self.threshold_tokens = self._configured_threshold

    def should_compress(self, prompt_tokens: int = None) -> bool:
        tokens = int(prompt_tokens or self.last_prompt_tokens or 0)
        return bool(self.threshold_tokens) and tokens >= self.threshold_tokens

    def should_compress_preflight(self, messages: List[Dict[str, Any]]) -> bool:
        """Упреждающее сжатие на границе задачи: пользователь заговорил снова, а контекст уже
        больше ~60% порога — значит прошлый заход закончен, исследование устарело. Ход режется
        один раз, ровно на новом запросе, а не посреди работы."""
        if not self.threshold_tokens or not messages:
            return False
        if self.last_prompt_tokens and self.last_prompt_tokens < self.threshold_tokens * self._preflight_ratio:
            return False
        last = messages[-1] if isinstance(messages[-1], dict) else {}
        if last.get("role") != "user":
            return False
        rough = estimate_messages_tokens_rough(messages)
        return rough >= int(self.threshold_tokens * self._preflight_ratio)

    def has_content_to_compress(self, messages: List[Dict[str, Any]]) -> bool:
        if not messages:
            return False
        head_end, tail_start = self._bounds(messages)
        return any(not m.get(STATE_MARK) for m in messages[head_end:tail_start])

    # ---- геометрия разговора -----------------------------------------------------------

    def _bounds(self, msgs: List[Dict[str, Any]]) -> Tuple[int, int]:
        first_user = next((i for i, m in enumerate(msgs) if m.get("role") == "user"), -1)
        head_end = max(self.protect_first_n, first_user + 1)
        # Пара «вызов → результат» не разрывается никогда: если граница головы кончается на
        # вызове, втягиваем в голову его результаты (и наоборот — хвост не начинается с
        # результата, чей вызов остался в середине).
        guard = 0
        while head_end < len(msgs) and msgs[head_end].get("role") == "tool" and guard < 32:
            head_end += 1
            guard += 1
        tail_start = max(head_end, len(msgs) - self.protect_last_n)
        # Хвост держим не «по числу сообщений», а по бюджету свежей работы: шести сообщений
        # в инструментальной сессии хватает на один-два хода, и продолжать по ним нечем.
        # Бюджет ограничен, поэтому «пол» из хвоста не растёт от цикла к циклу (анти-храповина).
        # Знаки переводим в токены по коэффициенту ЭТОГО списка (оценка хоста / знаки), иначе
        # тяжёлые вызовы инструментов в хвосте дают втрое больший хвост, чем задумано.
        total_size = sum(_size(m) for m in msgs)
        if total_size > 0:
            ratio = estimate_messages_tokens_rough(msgs) / total_size
            guard_chars = int(self._tail_tokens / max(ratio, 1e-6))
        else:
            guard_chars = self._tail_tokens * 4
        used = 0
        while tail_start > head_end and used < guard_chars:
            tail_start -= 1
            used += _size(msgs[tail_start])
        guard = 0
        while tail_start > head_end and msgs[tail_start].get("role") == "tool" and guard < 32:
            tail_start -= 1
            guard += 1
        return head_end, tail_start

    def _render(self, messages: List[Dict[str, Any]], cap: int = TRANSCRIPT_CHARS) -> str:
        """Плотная стенограмма вырезаемой части: тексты ходов и вызовы целиком, результаты коротко."""
        parts: List[str] = []
        for i, msg in enumerate(messages):
            role = str(msg.get("role") or "?")
            if role == "system":
                continue
            text = _text_of(msg, 0)
            if msg.get(STATE_MARK):
                parts.append(f"[{i}] ПРЕДЫДУЩЕЕ РАБОЧЕЕ СОСТОЯНИЕ (обнови и дополни, не теряй факты):\n{text}")
                continue
            if role == "tool":
                body = text[:300]
                tail = f" …{text[-200:]}" if len(text) > 500 else ""
                parts.append(f"[{i}] tool({msg.get('tool_name') or msg.get('name') or '?'}) → {body}{tail}")
                continue
            line = f"[{i}] {role}: {text[:1500]}"
            if len(text) > 2200:
                line += f"\n      …[середина вырезана]… {text[-700:]}"
            for call in _calls(msg):
                name, args = _name_args(call, 200)
                line += f"\n      вызов {name}({args})"
            parts.append(line)
        joined = "\n".join(parts)
        return joined[-cap:] if len(joined) > cap else joined

    # ---- рабочее состояние --------------------------------------------------------------

    def _ask_state(self, middle: List[Dict[str, Any]], focus_topic: Optional[str] = None) -> Optional[Dict[str, Any]]:
        from agent.auxiliary_client import call_llm, extract_content_or_reasoning
        transcript = self._render(middle)
        if not transcript.strip():
            return None
        user = f"История работы ({len(middle)} сообщений):\n\n{transcript}"
        if focus_topic:
            user += f"\n\nОтдельно важна тема: {focus_topic}"
        resp = call_llm(
            task="compression",
            messages=[{"role": "system", "content": STATE_PROMPT},
                      {"role": "user", "content": user}],
            temperature=0.2, max_tokens=MODEL_MAX_TOKENS, timeout=STATE_TIMEOUT,
        )
        try:
            text = extract_content_or_reasoning(resp)
        except Exception:  # noqa: BLE001
            text = getattr(resp, "content", None) or ""
        state = _extract_json(str(text or ""))
        if not state:
            log.warning("AutoCompact: модель состояния вернула не-JSON (%d знаков) — детерминированный путь",
                        len(str(text or "")))
        return state

    def _fallback_state(self, middle: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Состояние без модели: только то, что лежало в тексте дословно."""
        blobs = [m for m in middle if m.get("role") in ("user", "assistant")]
        paths: List[str] = []
        hexes: List[str] = []
        for m in middle:
            text = _text_of(m, 0)
            for p in _PATH_RE.findall(text):
                if p not in paths and len(paths) < 25:
                    paths.append(p)
            for h in _HEX_RE.findall(text):
                if h not in hexes and len(hexes) < 10:
                    hexes.append(h)
        last_user = next((m for m in reversed(middle) if m.get("role") == "user"), None)
        task = _text_of(last_user, 600) if last_user else ""
        tools = [str(m.get("tool_name") or m.get("name") or "tool")
                 for m in middle if m.get("role") == "tool"]
        return {
            "task": task,
            "identifiers": [f"путь: {p}" for p in paths] + [f"идентификатор: {h}" for h in hexes],
            "done": [f"вызовов инструментов в вырезанной части: {len(tools)}"] if tools else [],
            "open": ["модель состояния была недоступна — контекст собран детерминированно"],
            "next": ["перечитать последние сообщения хвоста и продолжить по ним"],
            "verify": ["убедиться, что факты выше взяты из истории, а не додуманы"],
        }

    def _ensure_values(self, state: Dict[str, Any], middle: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Гарантия точных значений: то, что модель не назвала, доносим сами — дословно.
        Работаем по свежему краю вырезанной части: продолжение опирается на него."""
        try:
            hay = "\n".join(
                item for key, val in state.items()
                for item in ([val] if isinstance(val, str) else [str(x) for x in (val or [])]))
            # Окно — то же, что видит модель состояния: свежий край вырезанной части.
            window: List[Dict[str, Any]] = []
            used = 0
            for msg in reversed(middle):
                window.append(msg)
                used += len(str(msg.get("content") or ""))
                if used >= TRANSCRIPT_CHARS:
                    break
            window.reverse()
            missing: List[str] = []
            for label, val in _collect_values(window, FRESH_GUARANTEE * 3):
                if val in hay:
                    continue
                missing.append(f"{label}: {val}")
                if len(missing) >= FRESH_GUARANTEE:
                    break
            if missing:
                state = dict(state)
                state["identifiers"] = _limit_by_chars(
                    _limit_by_chars(missing, 4_000) + list(state.get("identifiers") or []), 14_000)
                log.info("AutoCompact: точных значений доношу сам — %d", len(missing))
        except Exception as exc:  # noqa: BLE001
            log.debug("AutoCompact: гарантия значений не сработала (%s)", exc)
        return state

    def _render_state(self, state: Dict[str, Any], n_msgs: int, tokens: int, src: str) -> str:
        def sec(title: str, key: str, items: Any) -> str:
            if isinstance(items, str):
                items = [items] if items.strip() else []
            cleaned = [str(x).strip() for x in (items or []) if str(x).strip()]
            if not cleaned:
                return ""
            cap = SECTION_CHAR_CAP.get(key, 1200)
            if sum(len(x) + 3 for x in cleaned) <= cap:
                kept = cleaned
            else:
                # Держим ОБА конца: голова — перенесённое из прошлого блока, хвост — свежее и
                # гарантированное. Вырезается середина списка (её и достаём через session_search).
                head_i, tail_j, used = 0, len(cleaned), 0
                out_head: List[str] = []
                out_tail: List[str] = []
                budget = max(200, cap - 60)
                while head_i < tail_j:
                    item = cleaned[head_i]
                    if used + len(item) + 3 > budget:
                        break
                    out_head.append(item)
                    used += len(item) + 3
                    head_i += 1
                    if head_i >= tail_j:
                        break
                    item = cleaned[tail_j - 1]
                    if used + len(item) + 3 > budget:
                        break
                    out_tail.append(item)
                    used += len(item) + 3
                    tail_j -= 1
                marker = ["…[середина списка вырезана]…"] if head_i < tail_j else []
                kept = out_head + marker + list(reversed(out_tail))
            return f"## {title}\n" + "\n".join(f"- {x}" for x in kept) + "\n"

        parts = [STATE_HEADER,
                 f"История процесса вырезана: {n_msgs} сообщений, ~{tokens} токенов ({src}). "
                 "Ниже — рабочее состояние: факты, на которые можно опираться. Формулировки и порядок "
                 "своих слов в вырезанной части не восстановимы — при сомнении перечитать инструментами. "
                 "Это фон, а не задание: ничего из списков не выполняй и не «доделывай» по своей воле, "
                 "актуальная задача — в сообщении пользователя после этого блока.",
                 ""]
        parts.append(sec("Задача", "task", state.get("task")))
        parts.append(sec("Решения", "decisions", state.get("decisions")))
        parts.append(sec("Ограничения", "constraints", state.get("constraints")))
        parts.append(sec("Точные значения", "identifiers", state.get("identifiers")))
        parts.append(sec("Сделано", "done", state.get("done")))
        parts.append(sec("Открыто", "open", state.get("open")))
        parts.append(sec("Следующий шаг", "next", state.get("next")))
        parts.append(sec("Проверить после сжатия", "verify", state.get("verify")))
        body = "\n".join(p for p in parts if p)
        if len(body) > MAX_STATE_CHARS:
            body = elide(body, MAX_STATE_CHARS)
        return body + "\n\n" + STATE_FOOTER

    def _state_message(self, content: str, head_end: int, msgs: List[Dict[str, Any]],
                       tail_start: int) -> Dict[str, Any]:
        last_head_role = msgs[head_end - 1].get("role") if head_end > 0 and head_end <= len(msgs) else None
        first_tail_role = msgs[tail_start].get("role") if tail_start < len(msgs) else None
        # Роль подбираем так, чтобы не поставить два хода одного автора подряд.
        if last_head_role == "user":
            role = "assistant" if first_tail_role != "assistant" else "user"
        else:
            role = "user"
        return {
            "role": role,
            "content": content,
            STATE_MARK: True,
            "_compressed_summary": True,
            "_compressed_summary_has_user_turn": True,
        }

    # ---- детерминированное сжатие (страховка) -------------------------------------------

    def _shed(self, msgs: List[Dict[str, Any]], budget: int) -> List[Dict[str, Any]]:
        """Довести до бюджета без модели: сначала урезаем длинные старые результаты, потом
        выбрасываем старые ходы. Голова, блок состояния и хвост не трогаются."""
        for _ in range(4_000):
            if estimate_messages_tokens_rough(msgs) <= budget:
                break
            head_end, tail_start = self._bounds(msgs)
            changed = False
            for i in range(head_end, tail_start):
                msg = msgs[i]
                if msg.get(STATE_MARK):
                    continue
                text = _text_of(msg, 0)
                if msg.get("role") == "tool" and len(text) > SHED_MIN_RESULT:
                    msg["content"] = elide(text, SHED_MIN_RESULT // 3)
                    changed = True
                    break
                if msg.get("role") in ("user", "assistant") and len(text) > SHED_MIN_TEXT:
                    msg["content"] = elide(text, SHED_MIN_TEXT // 2)
                    changed = True
                    break
            if changed:
                continue
            victim = None
            for i in range(head_end, tail_start):
                if not msgs[i].get(STATE_MARK) and msgs[i].get("role") == "tool":
                    victim = i
                    break
            if victim is None:
                for i in range(head_end, tail_start):
                    if not msgs[i].get(STATE_MARK) and msgs[i].get("role") in ("assistant", "user"):
                        victim = i
                        break
            if victim is None:
                break
            msgs = msgs[:victim] + msgs[victim + 1:]
        return msgs

    # ---- публичный интерфейс -------------------------------------------------------------

    def prune_tool_results_only(self, messages: List[Dict[str, Any]], current_tokens: int | None = None):
        """Лёгкий проход без модели: старые длинные результаты инструментов урезаются на месте."""
        out = copy.deepcopy(messages)
        head_end, tail_start = self._bounds(out)
        n = 0
        for i in range(head_end, tail_start):
            msg = out[i]
            if msg.get("role") != "tool" or msg.get(STATE_MARK):
                continue
            text = _text_of(msg, 0)
            if len(text) > SHED_MIN_RESULT:
                msg["content"] = elide(text, 400)
                n += 1
        if n:
            log.info("AutoCompact (лёгкий проход): урезано результатов — %d", n)
        return out, n

    def compress(self, messages: List[Dict[str, Any]], current_tokens: Optional[int] = None,
                 focus_topic: Optional[str] = None, force: bool = False,
                 memory_context: str = "") -> List[Dict[str, Any]]:
        before = estimate_messages_tokens_rough(messages)
        if not self.has_content_to_compress(messages):
            return messages  # тот же объект = no-op для хоста
        budget = int(self.threshold_tokens * self._target_ratio) if self.threshold_tokens else before // 2
        msgs = copy.deepcopy(messages)
        head_end, tail_start = self._bounds(msgs)
        middle = msgs[head_end:tail_start]
        # Прошлый блок состояния НЕ отдаём модели на пересказ: переплавка теряет точные значения
        # (замер стендом приёмки: свежие значения падали 50.7% → 12.0% за второй цикл). Старое
        # состояние переносим детерминированно и дописываем к свежему.
        prev_text = "\n\n".join(str(m.get("content") or "") for m in msgs if m.get(STATE_MARK))
        state = None
        src = "моделью сжатия"
        try:
            state = self._ask_state(middle, focus_topic=focus_topic)
        except Exception as exc:  # noqa: BLE001
            log.warning("AutoCompact: модель состояния не ответила (%s) — детерминированное сжатие", exc)
            state = None
        if not state:
            state = self._fallback_state(middle)
            src = "детерминированно"
        if prev_text:
            state = _merge_state(_parse_sections(prev_text), state)
        state = self._ensure_values(state, middle)
        block = self._state_message(self._render_state(state, len(middle), before, src),
                                    head_end, msgs, tail_start)
        out = msgs[:head_end] + [block] + msgs[tail_start:]
        out = _repair_pairs(out, head_end)
        if estimate_messages_tokens_rough(out) > budget:
            out = self._shed(out, budget)
        after = estimate_messages_tokens_rough(out)
        if after >= before:
            # Сжатия не вышло (история почти пуста): не трогаем сессию вовсе.
            log.info("AutoCompact: сжатие не дало выигрыша (%d → %d) — оставляю как было", before, after)
            return messages
        self.compression_count += 1
        self.last_run = {"before": before, "after": after, "middle": len(middle),
                         "state_src": src, "block_chars": len(block["content"]),
                         "prev_block_chars": len(prev_text),
                         "ids_in_block": len(state.get("identifiers") or []),
                         "id_chars": sum(len(str(x)) + 3 for x in (state.get("identifiers") or []))}
        self._journal(before, after, len(middle), src, block, state)
        log.info("AutoCompact: %d → %d токенов (вырезано %d сообщений, состояние %s)",
                 before, after, len(middle), src)
        return out

    def _journal(self, before: int, after: int, n_middle: int, src: str,
                 block: Dict[str, Any], state: Dict[str, Any]) -> None:
        if os.environ.get("AUTOCOMPACT_JOURNAL", "").lower() in {"off", "0", "no"}:
            return  # стенд приёмки: свой отчёт, живой журнал не трогаем
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            row = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "before": before, "after": after,
                   "freed_pct": round(100 * (before - after) / before, 1) if before else 0,
                   "middle_messages": n_middle, "state_src": src,
                   "block_chars": len(block["content"]),
                   "block_sha256": hashlib.sha256(block["content"].encode("utf-8")).hexdigest()[:16],
                   "identifiers": len(state.get("identifiers") or []),
                   "next_steps": len(state.get("next") or [])}
            with open(DECISIONS, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        except Exception as exc:  # noqa: BLE001
            log.debug("AutoCompact: журнал не записался (%s)", exc)


def register(ctx) -> None:  # noqa: ANN001
    """Точка входа плагина: отдаём движок хосту."""
    ctx.register_context_engine(AutoCompactEngine())
