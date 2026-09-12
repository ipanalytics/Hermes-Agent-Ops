# 17 — model-slot-bakeoff

_Русская версия: [README.ru.md](README.ru.md)_

**A price list is dollars per million tokens. It does not tell you what one request costs.**

> A reasoning model can burn six times the output tokens of a plain one on the identical
> prompt, so the cheaper-per-token model ends up the more expensive one per task — and the
> slower one. The only way to know is to run the slot's real work through both and look at
> the bill, the clock, and whether the answer was actually correct.

## What you get

- `bakeoff.py` — runs one task set against N candidate models, grades each answer against a
  hidden test, and writes a JSON report plus a summary table.
- `examples/slot-check/` — a two-task set with hidden tests, and three candidates for a
  coding slot (a plain coder model, a reasoning model, and the same model with reduced
  reasoning effort).
- `tests/test_bakeoff.py` — offline tests for the grading, loading, and error paths.

## What it measures, per candidate

| Signal | Why it is in the report |
|---|---|
| `passed` | the hidden test decides, not the model's own claim — the candidate never sees the test |
| `avg_cost_per_task_usd` | the cost as billed by the gateway for that call, reasoning tokens included |
| `completion_tokens` | shows *why* a cheap-per-token model is expensive per task |
| `served_by` | routing is not always what you asked for; this is the upstream that answered |
| `avg_latency_s` | a slot on a user's critical path pays for a slow candidate on every request |
| `tool_call_ok` | with `--with-tools`: a model that never emits a tool call cannot hold an agent slot |

## How to use it

```bash
python3 bakeoff.py --candidates candidates.json --tasks tasks.json --with-tools
```

The API key is read from `OPENROUTER_API_KEY` (environment or `~/.hermes/.env`). Point
`BAKEOFF_API_URL` at any OpenAI-compatible endpoint to measure a different gateway.

Candidate list — the model under test, an optional upstream pin, and optional request fields
this is where a `reasoning_effort` variant becomes its own candidate:

```json
[
  {"label": "incumbent", "model": "vendor/model-a"},
  {"label": "challenger", "model": "vendor/model-b", "provider": "FirstPartyCloud"},
  {"label": "challenger (low effort)", "model": "vendor/model-b", "extra": {"reasoning_effort": "low"}}
]
```

Task set — a prompt plus the test that grades the answer. Grading runs the model's code block
against the test in a scratch directory, so tasks must be verifiable:

```json
[
  {"name": "flaky-input",
   "prompt": "Write a Python function `pick(items, key, k)` ... Answer with one ```python block only.",
   "test": "from solution import pick\nassert pick([{'n': 1}], 'n', 1) == [{'n': 1}]\nprint('OK')"}
]
```

## The measured example

`examples/slot-check`, two graded tasks, one run (all three candidates served by the same
first-party upstream, all three passed both hidden tests):

| candidate | pass | avg latency | avg cost / task | output tokens / task |
|---|---|---|---|---|
| plain coder model | 2/2 | 3.0 s | $0.00077 | 435 |
| reasoning model, default effort | 2/2 | 134.0 s | $0.01655 | 12 938 |
| reasoning model, low effort | 2/2 | 13.8 s | $0.00234 | 1 796 |

Identical correctness, 21× difference in what the slot costs per request and 45× in latency,
all of it spent on reasoning tokens the non-thinking model never produces. Cutting effort on
the reasoning model brings it back to 3× the plain model's cost with a quarter of the tokens.
The same task set on a different day, or with a different task mix, can move these numbers —
that is why the harness exists rather than a table of list prices.

## Three failures this catches that a price list hides

1. **Reasoning tokens.** Output is the expensive half of the bill and thinking models are
   billed for it. Comparing per-token prices across a thinking and a non-thinking model
   compares the wrong number.
2. **Routing.** `served_by` reports the upstream that actually answered. A model whose only
   upstreams sit outside the gateway account's allowed-provider list fails with
   `HTTP 404: No allowed providers are available for the selected model` even though the
   catalog lists it and its endpoint status is healthy — the error body names both the model's
   upstreams and the allow-list, and it is the only place that says why the model cannot be
   called. Pin with `"provider": "<name>"` once you know which upstream you want.
3. **Tool calls.** For an agent slot, tool-call support is a hard requirement, not a bonus.
   `--with-tools` probes it in a single request.

## Limits

- A handful of tasks is a smoke test, not a benchmark. It answers "which candidate is cheaper
  and still correct for *this* slot", not "which model is smarter".
- Cost is what the gateway reports for each call; cache hits and provider-side discounts are
  not simulated.
- Latency moves with upstream load: compare candidates within one run, not across days.
- The harness executes model-written Python to grade it. Keep hidden tests dependency-free and
  run it somewhere disposable when the models under test are not trusted.
