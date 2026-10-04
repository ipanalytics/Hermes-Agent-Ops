# 17 — model-slot-bakeoff

_Russian version: [README.ru.md](README.ru.md)_

A price list is dollars per million tokens. It does not tell me what one request costs. This module runs the same real tasks through several models, and tells me which one is correct, which is fast, and what each answer actually billed me.

> A reasoning model can burn six times the output tokens of a plain one on the identical prompt, so the cheaper-per-token model ends up the more expensive one per task — and the slower one. The only way to know is to run the slot's real work through both and look at the bill, the clock, and whether the answer was actually correct.

## Hermes, in one paragraph

Hermes is the AI agent that lives on my server. Each named role in his workload — research, coding, summarising, digesting — is a *slot*: one entry in his config that says "for this kind of task, use model X by default". The slot can be swapped (a new model lands, a price changes, the old one gets de-listed) and when that happens, I need to know whether the swap is safe: is the new model correct enough, is it fast enough, is it cheaper, does it still support tool calls if the slot needs them. This folder is the harness that answers those four questions with numbers instead of with guesses.

## What I have

- `bakeoff.py` — runs one task set against N candidate models, grades each answer against a hidden test, and writes a JSON report plus a summary table.
- `examples/slot-check/` — a two-task set with hidden tests, and three candidates for a coding slot (a plain coder model, a reasoning model, and the same model with reduced reasoning effort).
- `tests/test_bakeoff.py` — offline tests for the grading, loading, and error paths.

## The vocabulary I use here

A *token* is roughly a word or part of a word, the unit the API bills by. A *reasoning model* is one that thinks out loud before answering — and I pay for every word of that thinking. So a model that looks cheap in the catalogue can quietly cost six times more per task than its plain-looking rival.

A *gateway* is the middleman service I send requests to (OpenRouter in my case, but anything OpenAI-shaped works). An *upstream* is the company behind the model that actually answered — the gateway picks it, and not always the one I meant. The API key I read is `OPENROUTER_API_KEY`, kept either in the environment or in `~/.hermes/.env`.

A *hidden test* is a small check I write myself; the model gets the task but never the test, so "passed" means the answer really works. The harness runs the model's code block against the test in a scratch directory using `subprocess.run` with a timeout, so a wrong solution prints a one-line error tail and a correct one prints `OK`. The model's own claim of success is not part of the test.

A *tool call* is the model asking to run one of the agent's tools — without that, a model can't be an agent at all. *Latency* is just how long one answer takes, measured at my side between request sent and response read. *Cost* is what the gateway reports for each call (`usage.cost` in the response): reasoning tokens are already in the bill, no separate accounting.

## What I measure, per candidate

| Signal | Why it is in the report |
|---|---|
| `passed` | the hidden test decides, not the model's own claim — the candidate never sees the test |
| `avg_cost_per_task_usd` | the cost as billed by the gateway for that call, reasoning tokens included |
| `completion_tokens` | shows *why* a cheap-per-token model is expensive per task |
| `served_by` | routing is not always what I asked for; this is the upstream that answered |
| `avg_latency_s` | a slot on a user's critical path pays for a slow candidate on every request |
| `tool_call_ok` | with `--with-tools`: a model that never emits a tool call cannot hold an agent slot |

The first three columns — pass, cost, tokens — together answer "is the swap correct and what does it cost?". The fourth, `served_by`, is what catches the cases where the catalogue lies. The fifth is what I check before I put a candidate on a hot path. The sixth is what makes an agent slot an agent slot.

## How I use it

```bash
python3 bakeoff.py --candidates candidates.json --tasks tasks.json --with-tools
```

The API key is read from `OPENROUTER_API_KEY` (environment or `~/.hermes/.env`). I point `BAKEOFF_API_URL` at any OpenAI-compatible endpoint to measure a different gateway — the script uses urllib against the standard `chat/completions` path, so any drop-in replacement works. The default URL is `https://openrouter.ai/api/v1/chat/completions`. `--out` controls where the JSON report lands (default `bakeoff-report.json`). `--max-tokens` caps the model's reply; the default is 2000. Exit code is 0 on a completed run and 2 on a setup error (no key, bad input).

The candidate list is the model under test, an optional upstream pin, and optional request fields — this is where a `reasoning_effort` variant becomes its own candidate:

```json
[
  {"label": "incumbent", "model": "vendor/model-a"},
  {"label": "challenger", "model": "vendor/model-b", "provider": "FirstPartyCloud"},
  {"label": "challenger (low effort)", "model": "vendor/model-b", "extra": {"reasoning_effort": "low"}}
]
```

`label` is what shows up in the table; if missing, the model id is used. A candidate without a `model` field is rejected up front, before any request leaves. The `provider` field becomes a hard pin (`{"only": [provider]}` in the request body) — the gateway will refuse to fall back to anyone else. The `extra` field is merged into the request body as-is, which is how `reasoning_effort`, sampling overrides and the like get in.

The task set is a prompt plus the test that grades the answer. Grading runs the model's code block against the test in a scratch directory, so tasks must be verifiable:

```json
[
  {"name": "flaky-input",
   "prompt": "Write a Python function `pick(items, key, k)` ... Answer with one ```python block only.",
   "test": "from solution import pick\nassert pick([{'n': 1}], 'n', 1) == [{'n': 1}]\nprint('OK')"}
]
```

The harness extracts the first fenced `python` block from the model's answer and runs the test against it. If no fenced block exists, the whole answer is treated as code — useful for terse candidates that just print the function. A test that imports `solution` is the canonical shape; the harness writes the model's code to `solution.py` and the test to `test_solution.py` in a `tempfile.TemporaryDirectory`. `jsonl` is accepted as well as plain JSON arrays, which is what I use when a task set grows past a handful of items.

## The measured example

`examples/slot-check`, two graded tasks, one run (all three candidates served by the same first-party upstream, all three passed both hidden tests):

| candidate | pass | avg latency | avg cost / task | output tokens / task |
|---|---|---|---|---|
| plain coder model | 2/2 | 3.0 s | $0.00077 | 435 |
| reasoning model, default effort | 2/2 | 134.0 s | $0.01655 | 12 938 |
| reasoning model, low effort | 2/2 | 13.8 s | $0.00234 | 1 796 |

I measured identical correctness across all three, a 21× difference in what the slot costs per request and 45× in latency — and every cent of that difference was reasoning tokens the non-thinking model never produces. Cutting effort on the reasoning model brings it back to 3× the plain model's cost with a quarter of the tokens. That one table is the whole point: the price list would have picked the reasoning model, and I would have paid 21× for the same answers. The same task set on a different day, or with a different task mix, can move these numbers — that is why I run a harness instead of trusting a table of list prices.

The third row is the one I tend to keep. The reasoning model with default effort is correct but expensive and slow; the same model with low effort is correct, cheap-ish, and only four seconds slower than the plain one. That is usually the swap.

## Three failures this catches that a price list hides

1. **Reasoning tokens.** Output is the expensive half of the bill and thinking models are billed for it. Comparing per-token prices across a thinking and a non-thinking model compares the wrong number — what I need is per-task cost on the same task set.
2. **Routing.** `served_by` reports the upstream that actually answered. A model whose only upstreams sit outside the gateway account's allowed-provider list fails with `HTTP 404: No allowed providers are available for the selected model` even though the catalog lists it and its endpoint status is healthy — the error body names both the model's upstreams and the allow-list, and it is the only place that says why the model cannot be called. I pin with `"provider": "<name>"` once I know which upstream I want. The harness keeps the body in the per-task error string so the routing reason survives into the JSON report.
3. **Tool calls.** For an agent slot, tool-call support is a hard requirement, not a bonus. `--with-tools` probes it in a single request: a fixed prompt ("List the files in /tmp with the shell tool.") with a one-function tool definition in the request body. A model that emits the expected function call gets `tool_call_ok: yes`; a model that answers in prose gets `tool_call_ok: no`; a model that errors gets the error text and `no`.

## The JSON report

`--out` writes a CSV-style summary to stdout and a structured report to disk:

```json
{
  "candidates": [
    {
      "label": "incumbent", "model": "vendor/model-a",
      "provider_pin": null, "extra": null,
      "tasks": [
        {"name": "task-1", "served_by": "...", "latency_s": 3.0,
         "prompt_tokens": 412, "completion_tokens": 130,
         "reasoning_tokens": 0, "cost_usd": 0.00012,
         "verdict": "pass"}
      ],
      "totals": {"tasks": 2, "passed": 2, "cost_usd": 0.00154,
                 "avg_cost_per_task_usd": 0.00077,
                 "avg_latency_s": 3.0, "completion_tokens": 435},
      "tools": {"tool_call_ok": true, "tool_call_s": 2.4}
    }
  ],
  "tasks": 2
}
```

That file is what I commit next to the slot's config: a frozen snapshot of what the candidates cost at that point in time. Six months later, when the slot's cost creeps up or a swap gets proposed, the old report is what I compare the new run against.

## How often I run it

- Every time the catalogue changes the price of the slot's current model.
- Every time I consider swapping the incumbent for a candidate that looks cheaper on paper.
- After any prompt rewrite that might shift the slot's task shape — a different prompt tends to move the token count, which moves the bill.
- Once a quarter, on the same task set, to spot a quiet degradation in the incumbent before it shows up in production.

## Limits

- A handful of tasks is a smoke test, not a benchmark. It answers "which candidate is cheaper and still correct for *this* slot", not "which model is smarter".
- Cost is what the gateway reports for each call; cache hits and provider-side discounts are not simulated.
- Latency moves with upstream load: I compare candidates within one run, not across days.
- The harness executes model-written Python to grade it. I keep hidden tests dependency-free and run it somewhere disposable when the models under test are not trusted.