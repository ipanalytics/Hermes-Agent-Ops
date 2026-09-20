#!/usr/bin/env python3
"""multi-model-consilium — one model proposes, a second model attacks the proposal, the first
model answers the attack and commits to a plan.

Why: a single answer from a single model is a single point of failure. For decisions with
checkable criteria (architecture, budgets, migrations, contracts) a second model from a
different family finds holes the author cannot see, and making the author answer the attack
in writing forces the weak parts into the open. The transcript is kept, so the rejected
objections and the accepted ones are both on record.

The tool is provider-agnostic: any OpenAI-compatible /chat/completions endpoint works.

    python3 consilium.py --question "..." --base-url https://openrouter.ai/api/v1 \
        --model-a vendor/fast-model --model-b other/vendor-model --out-dir ./out
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import sys
import time
import urllib.error
import urllib.request

PROMPT_PROPOSAL = (
    "You are the engineer who owns this decision. Give a concrete plan: steps, order, the "
    "risks you know about, and the checks that would prove each step worked. State every "
    "assumption explicitly. No filler, no 'it depends' without naming what it depends on. "
    "At most 450 words."
)
PROMPT_REVIEW = (
    "You are a hostile reviewer. You are given a question and someone else's plan. Find "
    "concrete holes: wrong assumptions, missing edge cases, unverified claims, cost and "
    "blast radius, what breaks first in production. Every objection must be checkable or "
    "given as an example. No taste, no 'consider'. If the plan is sound, say so and why. "
    "At most 400 words."
)
PROMPT_SYNTHESIS = (
    "You wrote the plan below. Answer the attack: say which objections you accept and how "
    "you change the plan, which you reject and why, then give the final plan as steps. Do "
    "not restate the attack. At most 400 words."
)


def http_post(url: str, body: bytes, headers: dict, timeout: int) -> dict:
    """Default transport. Kept separate so tests can inject a fake one."""
    req = urllib.request.Request(url, data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def chat(base_url: str, api_key: str, model: str, messages: list, max_tokens: int = 1600,
         temperature: float = 0.2, timeout: int = 300, retries: int = 3,
         transport=None, sleep=time.sleep) -> tuple:
    """One completion. Returns (text, usage). A reply cut off by the token limit is retried
    with a doubled limit; if that still truncates, the cut text is returned with a marker
    instead of silently feeding half an answer into the next stage."""
    post = transport or http_post
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    limit, usage_acc, truncated, last = max_tokens, {"prompt_tokens": 0, "completion_tokens": 0}, "", ""
    for attempt in range(1, retries + 1):
        payload = {"model": model, "messages": messages, "temperature": temperature,
                   "max_tokens": limit}
        try:
            data = post(url, json.dumps(payload).encode(), headers, timeout)
            if data.get("error"):
                last = str(data["error"])[:200]
            else:
                choice = (data.get("choices") or [{}])[0]
                message = choice.get("message") or {}
                text = (message.get("content") or "").strip() or (message.get("reasoning") or "").strip()
                usage = data.get("usage") or {}
                for key in usage_acc:
                    usage_acc[key] += int(usage.get(key) or 0)
                if not text:
                    last = "empty response"
                elif choice.get("finish_reason") == "length":
                    truncated = text
                    last = f"truncated at {limit} tokens"
                    limit = min(limit * 2, 8000)
                else:
                    return text, usage_acc
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError) as exc:
            last = f"{type(exc).__name__}: {exc}"[:200]
        print(f"  attempt {attempt}/{retries} — {last}", file=sys.stderr)
        sleep(2 * attempt)
    if truncated:
        return truncated + "\n\n[reply truncated by the token limit — raise --max-tokens]", usage_acc
    raise RuntimeError(f"{model}: no usable reply ({last})")


def run_consilium(question: str, call, model_a: str, model_b: str, max_tokens: int = 1600) -> dict:
    """Three stages against an injectable `call(model, messages, max_tokens) -> (text, usage)`."""
    stages = []
    started = time.time()
    proposal, usage_a = call(model_a, [{"role": "system", "content": PROMPT_PROPOSAL},
                                       {"role": "user", "content": question}], max_tokens)
    stages.append({"stage": "proposal", "model": model_a, "text": proposal, "usage": usage_a})
    review, usage_b = call(model_b, [{"role": "system", "content": PROMPT_REVIEW},
                                     {"role": "user", "content":
                                      f"QUESTION:\n{question}\n\nPLAN:\n{proposal}"}], max_tokens)
    stages.append({"stage": "review", "model": model_b, "text": review, "usage": usage_b})
    synthesis, usage_c = call(model_a, [{"role": "system", "content": PROMPT_SYNTHESIS},
                                        {"role": "user", "content":
                                         f"QUESTION:\n{question}\n\nYOUR PLAN:\n{proposal}\n\n"
                                         f"ATTACK:\n{review}"}], max_tokens)
    stages.append({"stage": "synthesis", "model": model_a, "text": synthesis, "usage": usage_c})
    totals = {key: sum(s["usage"].get(key, 0) for s in stages)
              for key in ("prompt_tokens", "completion_tokens")}
    return {"question": question, "model_a": model_a, "model_b": model_b, "stages": stages,
            "tokens": totals, "seconds": round(time.time() - started, 1)}


def render(record: dict) -> str:
    lines = [f"# Consilium — {record['model_a']} vs {record['model_b']}",
             f"_tokens: {record['tokens']['prompt_tokens']} in / "
             f"{record['tokens']['completion_tokens']} out, {record['seconds']} s_", "",
             "## Question", "", record["question"], ""]
    titles = {"proposal": "1. Plan (author)", "review": "2. Attack (reviewer)",
              "synthesis": "3. Final plan (author answers the attack)"}
    for stage in record["stages"]:
        lines += [f"## {titles.get(stage['stage'], stage['stage'])} — `{stage['model']}`", "",
                  stage["text"], ""]
    return "\n".join(lines)


def slug(text: str, limit: int = 40) -> str:
    out = re.sub(r"[^A-Za-z0-9]+", "-", text[:limit]).strip("-")
    return out or "question"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="multi-model consilium: propose, attack, settle")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--question")
    src.add_argument("--question-file")
    ap.add_argument("--base-url", default=os.environ.get("CONSILIUM_BASE_URL",
                                                         "https://openrouter.ai/api/v1"))
    ap.add_argument("--api-key-env", default="OPENROUTER_API_KEY")
    ap.add_argument("--model-a", default="")
    ap.add_argument("--model-b", default="")
    ap.add_argument("--max-tokens", type=int, default=1600)
    ap.add_argument("--out-dir", default="consilium-out")
    ap.add_argument("--print", dest="print_synthesis", action="store_true", default=True)
    args = ap.parse_args(argv)

    if not args.model_a or not args.model_b:
        raise SystemExit("--model-a and --model-b are required")
    api_key = os.environ.get(args.api_key_env, "")
    if not api_key:
        raise SystemExit(f"{args.api_key_env} is not set")
    question = args.question or pathlib.Path(args.question_file).read_text(encoding="utf-8")

    def call(model, messages, max_tokens):
        return chat(args.base_url, api_key, model, messages, max_tokens)

    record = run_consilium(question, call, args.model_a, args.model_b, args.max_tokens)
    out_dir = pathlib.Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{time.strftime('%Y%m%d-%H%M%S')}-{slug(question)}.md"
    target.write_text(render(record), encoding="utf-8")
    if args.print_synthesis:
        print(record["stages"][-1]["text"])
    print(f"\n[transcript: {target}; tokens {record['tokens']['prompt_tokens']}+"
          f"{record['tokens']['completion_tokens']}; {record['seconds']} s]", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
