#!/usr/bin/env python3
"""model-slot bakeoff — pick a model for a slot by measuring the task, not the price list.

A price list tells you dollars per million tokens. It does not tell you what one request
costs: a reasoning model can spend six times the output tokens of a plain one on the same
prompt, and a three-second answer is worth more than a nine-cent one when the slot is on a
user's critical path.

This harness runs one task set against N candidate models and reports, per candidate:

  * latency, prompt/completion tokens, actual cost (as billed by the gateway),
  * which upstream provider served the request (routing is not always what you asked for),
  * whether the returned code passes a hidden test the model never sees,
  * whether the model answers tool calls at all, if the slot needs them.

Candidates are described in a JSON file, so the same run can compare a slot's current model,
a cheaper alternative, and a variant with different reasoning settings.

Usage:
  bakeoff.py --candidates candidates.json --tasks tasks.jsonl --out report.json
  bakeoff.py --candidates candidates.json --tasks tasks.jsonl --with-tools

Exit codes: 0 run completed, 2 setup error (no key / bad input).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

API_URL = os.environ.get("BAKEOFF_API_URL", "https://openrouter.ai/api/v1/chat/completions")
MODELS_URL = os.environ.get("BAKEOFF_MODELS_URL", "https://openrouter.ai/api/v1/models")
CODE_BLOCK = re.compile(r"```(?:python|py)?\s*(.*?)```", re.S)


def api_key() -> str | None:
    key = os.environ.get("OPENROUTER_API_KEY")
    if key:
        return key
    env = Path.home() / ".hermes" / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("OPENROUTER_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def load_json(path: str | Path):
    text = Path(path).read_text(encoding="utf-8")
    if str(path).endswith(".jsonl"):
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    return json.loads(text)


def load_candidates(path: str | Path) -> list[dict]:
    rows = load_json(path)
    if not isinstance(rows, list) or not rows:
        raise SystemExit("candidates file must be a non-empty JSON array")
    for row in rows:
        row.setdefault("label", row.get("model"))
        if not row.get("model"):
            raise SystemExit(f"candidate without a model id: {row}")
    return rows


def load_tasks(path: str | Path) -> list[dict]:
    rows = load_json(path)
    if not isinstance(rows, list) or not rows:
        raise SystemExit("task file must be a non-empty JSON array or JSONL")
    for row in rows:
        if "prompt" not in row:
            raise SystemExit(f"task without a prompt: {str(row)[:80]}")
        row.setdefault("name", f"task-{rows.index(row) + 1}")
    return rows


def extract_code(text: str) -> str:
    """Return the first fenced code block, or the whole answer if there is none."""
    match = CODE_BLOCK.search(text or "")
    return (match.group(1) if match else (text or "")).strip()


def grade(code: str, test: str | None, timeout: int = 60) -> str:
    """Run *test* against the candidate's code in a scratch directory."""
    if not test:
        return "not graded"
    with tempfile.TemporaryDirectory(prefix="bakeoff-") as workdir:
        Path(workdir, "solution.py").write_text(code or "", encoding="utf-8")
        Path(workdir, "test_solution.py").write_text(test, encoding="utf-8")
        try:
            proc = subprocess.run([sys.executable, "test_solution.py"], cwd=workdir,
                                  capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return "fail: timeout"
        if proc.returncode == 0:
            return "pass"
        tail = (proc.stderr.strip().splitlines() or ["non-zero exit"])[-1]
        return f"fail: {tail[:140]}"


def describe_http_error(exc: urllib.error.HTTPError) -> str:
    """Keep the body: 'no allowed providers' 404s carry the routing fix in the text."""
    try:
        body = exc.read().decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        body = ""
    body = " ".join(body.split())
    return f"HTTP {exc.code}: {body[:400]}" if body else f"HTTP {exc.code}"


def call_model(model: str, prompt: str, key: str, max_tokens: int, provider: str | None,
               extra: dict | None, tools: list | None = None) -> dict:
    body: dict = {"model": model, "messages": [{"role": "user", "content": prompt}],
                  "max_tokens": max_tokens}
    if provider:
        body["provider"] = {"only": [provider]}
    if tools:
        body["tools"] = tools
    if extra:
        body.update(extra)
    request = urllib.request.Request(
        API_URL, data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    started = time.time()
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            data = json.load(response)
    except urllib.error.HTTPError as exc:
        return {"error": describe_http_error(exc), "latency_s": round(time.time() - started, 1)}
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}",
                "latency_s": round(time.time() - started, 1)}
    choice = data["choices"][0]
    message = choice["message"]
    usage = data.get("usage") or {}
    return {
        "served_by": data.get("provider"),
        "latency_s": round(time.time() - started, 1),
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "reasoning_tokens": usage.get("completion_tokens_details", {}).get("reasoning_tokens"),
        "cost_usd": usage.get("cost"),
        "finish_reason": choice.get("finish_reason"),
        "answer": message.get("content") or "",
        "tool_calls": [c["function"]["name"] for c in (message.get("tool_calls") or [])],
    }


TOOL_PROBE = [{
    "type": "function",
    "function": {
        "name": "run_shell",
        "description": "Run a shell command",
        "parameters": {"type": "object", "properties": {"cmd": {"type": "string"}},
                       "required": ["cmd"]},
    },
}]


def probe_tools(model: str, key: str, provider: str | None) -> dict:
    result = call_model(model, "List the files in /tmp with the shell tool.", key,
                        max_tokens=300, provider=provider, extra=None, tools=TOOL_PROBE)
    if "error" in result:
        return {"tool_call_ok": False, "error": result["error"]}
    return {"tool_call_ok": result["tool_calls"] == ["run_shell"],
            "tool_call_s": result["latency_s"]}


def run(candidates: list[dict], tasks: list[dict], key: str, max_tokens: int,
        with_tools: bool) -> list[dict]:
    results = []
    for candidate in candidates:
        row = {"label": candidate["label"], "model": candidate["model"],
               "provider_pin": candidate.get("provider"),
               "extra": candidate.get("extra"), "tasks": []}
        totals = {"cost_usd": 0.0, "latency_s": 0.0, "completion_tokens": 0, "passed": 0}
        for task in tasks:
            call = call_model(candidate["model"], task["prompt"], key, max_tokens,
                              candidate.get("provider"), candidate.get("extra"))
            if "error" in call:
                row["tasks"].append({"name": task["name"], "error": call["error"],
                                     "latency_s": call["latency_s"]})
                continue
            call["name"] = task["name"]
            call["verdict"] = grade(extract_code(call.pop("answer")), task.get("test"))
            call.pop("tool_calls", None)
            totals["cost_usd"] += call.get("cost_usd") or 0.0
            totals["latency_s"] += call.get("latency_s") or 0.0
            totals["completion_tokens"] += call.get("completion_tokens") or 0
            totals["passed"] += 1 if call["verdict"] == "pass" else 0
            row["tasks"].append(call)
        row["totals"] = {
            "tasks": len(tasks),
            "passed": totals["passed"],
            "cost_usd": round(totals["cost_usd"], 5),
            "avg_cost_per_task_usd": round(totals["cost_usd"] / max(1, len(tasks)), 5),
            "avg_latency_s": round(totals["latency_s"] / max(1, len(tasks)), 1),
            "completion_tokens": totals["completion_tokens"],
        }
        if with_tools:
            row["tools"] = probe_tools(candidate["model"], key, candidate.get("provider"))
        results.append(row)
    return results


def print_table(results: list[dict]) -> None:
    header = (f"{'candidate':28s} {'served by':11s} {'pass':6s} {'avg s':7s} "
              f"{'avg $/task':11s} {'out tok':8s} {'tools':6s}")
    print(header)
    print("-" * len(header))
    for row in results:
        first = next((t for t in row["tasks"] if "error" not in t), {})
        totals = row["totals"]
        tools = row.get("tools", {}).get("tool_call_ok")
        print(f"{row['label'][:28]:28s} {str(first.get('served_by') or '-')[:11]:11s} "
              f"{totals['passed']}/{totals['tasks']:<4} {totals['avg_latency_s']:<7} "
              f"{totals['avg_cost_per_task_usd']:<11} {totals['completion_tokens']:<8} "
              f"{'yes' if tools else ('-' if tools is None else 'no')}")
        for task in row["tasks"]:
            if "error" in task:
                print(f"    ! {task['name']}: {task['error']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Measure model candidates on a real task set")
    parser.add_argument("--candidates", required=True, help="JSON array of candidates")
    parser.add_argument("--tasks", required=True, help="JSON array or JSONL of tasks")
    parser.add_argument("--out", default="bakeoff-report.json")
    parser.add_argument("--max-tokens", type=int, default=2000)
    parser.add_argument("--with-tools", action="store_true",
                        help="also probe whether the model answers tool calls")
    args = parser.parse_args()

    key = api_key()
    if not key:
        print("no OPENROUTER_API_KEY (env or ~/.hermes/.env)", file=sys.stderr)
        return 2
    candidates = load_candidates(args.candidates)
    tasks = load_tasks(args.tasks)
    results = run(candidates, tasks, key, args.max_tokens, args.with_tools)
    print_table(results)
    Path(args.out).write_text(json.dumps({"candidates": results, "tasks": len(tasks)},
                                         indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nreport: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
