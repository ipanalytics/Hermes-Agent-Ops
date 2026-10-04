# 35 — Context Compaction Engine

_Russian version: [README.ru.md](README.ru.md)_

![License](https://img.shields.io/github/license/ipanalytics/Hermes-Agent-Ops)
![Status](https://img.shields.io/badge/status-active-brightgreen)
![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue)

A context-compaction engine for Hermes Agent that replaces a long session with a **working state** — task, decisions, constraints, exact values, next step — instead of a summary of the conversation, plus the acceptance harness that judges a compaction by whether the task can still be finished afterwards.

## What this folder is, and the words it uses

Before the rest makes sense, a short glossary — the rest of the README and the source code itself use these terms and I don't want a first-time reader to bounce off them.

- **Hermes** is the name of my home AI agent. It runs on a server I own, talks to me through Telegram, schedules its own jobs, and runs long sessions where the user and the assistant exchange hundreds of messages on a single task.
- A **model** is the program that actually answers — the LLM (large language model). Different models are different products from different companies: one might be fast and cheap, another slow and careful, another tuned for code.
- A **provider** is the company that serves the model over an API. The model and the provider are not the same thing: the same model can be sold by more than one provider, and each provider has its own account, rate limits and billing. When I say "I changed the provider", I mean the billing counter, not the brain.
- A **token** is the unit the provider charges and the unit the model has a budget for. Roughly, a token is a piece of a word — for English prose, a token is on average about four characters. Everything has a price per token, and the model has a hard ceiling on how many tokens of conversation it can read at once. That ceiling is what I keep hitting.
- A **session** is one ongoing conversation between me and Hermes: a system prompt, then a back-and-forth of user and assistant turns, with tool calls and tool results in between. A session is stored as a list of message dicts; tokens are summed from that list.
- A **cron** (or "scheduled job") is a job that fires unattended at a fixed time. Daily digests, hourly checks, overnight sweeps — they all live in the same scheduler. This folder is not about cron, but it matters because the model ceiling matters most on the long sessions those jobs accumulate.
- The **context** is everything the model sees on its next turn: the system prompt, every prior message, and the latest user message. When the context is too big for the ceiling, nothing fits and the next turn fails — and that is the problem this folder solves.
- **Compaction** is the act of replacing part of the context with a smaller stand-in that still lets the work continue. The hard part is not "make it shorter". The hard part is "make it shorter without breaking the work".
- A **plugin** in this repo is a small Python file the host picks up by name from `~/.hermes/plugins/`. The engine in this folder registers itself as a context engine plugin through the function `register(ctx)`.

So: when a session is too big for the model ceiling, this engine replaces the middle of the conversation with a structured **state block** and leaves the head and the tail of the conversation untouched. The state block is the engine's whole product.

## Why I wrote it

The engine I ran before this one removed stale tool results and never shortened the user or assistant text itself. Over one week of real sessions that design fails exactly where it matters: the text floor grows with every cycle (43K → 139K, 91K → 240K, 175K → 359K tokens in three long sessions), the share freed by a compaction falls each time it runs (89% → 55%, 76% → 20%, 63% → 8%), and one session sitting on a 200K window stopped compacting altogether — 0% freed, the context pinned at the ceiling.

Two things caused it, and both are design, not tuning:

1. **Compaction was triggered by volume.** "It crossed the threshold — cut it." Nothing decided whether the work in that window was still needed; a finished research pass and a half-written file looked the same.
2. **Nothing measured the result.** Freeing 90% of a context is easy if I am willing to lose the thread: drop the middle, keep the last few turns, and the number looks excellent. The only quality signal was how the session felt afterwards, noticed days later.

So this module is a replacement, not a patch: compact the *work*, and accept the compaction by *continuation*.

## What it does

1. **When to compact.** Not only at the wall. Compaction also fires on a task boundary: the user speaks again and the context is already past ~60% of the threshold, which means the previous pass of work is finished and stale (`should_compress_preflight`). The hard threshold stays as a safety net (`should_compress`).
2. **What to keep.** Instead of a narrative of the process, the working state: the task, decisions and why, constraints, **exact values verbatim** (paths, ids, keys, commands, error texts, numbers), what is done, what is open, the next step, and what to re-read after the compaction. A cheap auxiliary model writes it; the compaction never asks a decision model to write prose.
3. **How to continue.** The state block sits immediately after the protected head; the last `tail_tokens` of fresh work stay verbatim. The block is marked, so on the next cycle it is not cut again — it is **carried**: the previous block's sections are parsed and merged into the new one *without asking the model to re-summarise them*, which is where exact values used to die.
4. **How to verify.** Every compaction is journalled (`data/autocompact_decisions.jsonl`) and accepted by `resume_eval.py`: does a session that sees only the compacted context still know what it was doing.

## What is in this folder

| File | Responsibility |
|---|---|
| `autocompact.py` | the engine itself: a Hermes context-engine plugin. Exposes `AutoCompactEngine`, the public `compress(...)` call, the deterministic fallback when the model is unreachable, the journal row written to `data/autocompact_decisions.jsonl`, and the `register(ctx)` entry point the host calls to wire it in. |
| `resume_eval.py` | the acceptance harness. Reads a *copy* of the state database (the live one is refused), runs one or two compression cycles, and scores exact-value survival, the no-stack invariant, and — with `--live` — a quiz where a fresh session answers questions about the cut-out part. |
| `examples/engine_config.yaml` | the keys the host reads from `config.yaml` under `compression:`, with their defaults. |
| `examples/state_block.md` | a rendered state block, the format `_render_state` produces. Useful as a reference when reading the journal. |
| `tests/test_state_sections.py` | offline tests for the deterministic parts: section round-trip, carry-over, the eviction window, the no-op contract, the model-failure path. Runs without the host, without the network, without a database. |
| `README.md` / `README.ru.md` | this document, in two languages. |

## The geometry of a compaction

Before the model is ever called, the engine splits the message list into three regions. Two are sacred and one is the working area:

- **Head.** From the first message up to the first state block (or the start of the session if there is none yet). The head is *never* touched. It holds the system prompt and the role-aware setup at the top of the session, and it is the contract the model was started under.
- **Middle.** Everything between the head and the tail. This is the region the model of the working state sees. The state block replaces it.
- **Tail.** The last `autocompact_tail_tokens` tokens of fresh work. The tail is *never* touched either — it is what the model on the next turn was literally looking at, and cutting it would invalidate the context the user just produced.

When two state blocks already exist (very rare, but possible if a manual edit went wrong), the head is everything up to the *first* one and the middle starts after it. The second one is then carried forward like any other previous block. After compression, `compress()` runs `_repair_pairs` to make sure tool calls and tool results still line up: an `assistant` turn with a `tool_call_id` must be followed by a matching `tool` turn, and orphans on either side are dropped.

## When compression fires

Two triggers, both exposed on the engine:

- **`should_compress(messages, current_tokens)`.** The wall. If the rough token estimate is past `threshold_tokens` (default `250_000`), compaction is forced. This is the safety net — it is allowed to be crude because by the time it fires the model is already close to failing its next turn.
- **`should_compress_preflight(messages, current_tokens)`.** The boundary. If the user just spoke (a fresh `user` message arrived at the tail) and the token count is past `threshold_tokens * autocompact_preflight_ratio` (default `0.6`), compaction fires *before* the next turn starts. The intuition: a user turn that follows a long passage of work means the previous pass is over. There is no point carrying the whole conversation into the next task.

The preflight trigger is the one that actually keeps a session healthy. The wall trigger is the one that keeps a session alive.

## The state block

The block is the whole product of a compaction. Exact values are an eviction window, not a dump: freshest on top, the oldest drops off first, and the cap is deliberately twice the size a single cycle produces, so the values from the previous block survive the next cycle intact.

```
## Задача
- <what is being done, and why>
## Решения
- <decision> — <reason>
## Ограничения
- <what must not be done>
## Точные значения
- путь: /srv/app/bin/collect.py
- файл: releases-collect.timer
- команда: systemctl list-timers --all
## Сделано
## Открыто
## Следующий шаг
## Проверить после сжатия
```

Eight sections, and the names are part of the contract:

- **Задача (task).** One line: what is being done, and why. The next cycle parses this back as a string and overwrites whatever was there before.
- **Решения (decisions).** Decisions taken and the reason each one was taken. Kept as a list because more than one decision accumulates in a long task.
- **Ограничения (constraints).** Things that must not be done — a negative space, useful when the next turn might be tempted to do them.
- **Точные значения (identifiers).** The only section that is allowed to be lossy. Paths, ids, file names, unit names, commands, error strings, numbers — anything that cannot be re-derived. Freshest at the top, oldest drops off the bottom first.
- **Сделано (done).** What is finished.
- **Открыто (open).** What is still open.
- **Следующий шаг (next).** The single next step the assistant should take on the next turn. One line, ideally.
- **Проверить после сжатия (verify).** A short list of things the assistant should re-read after the compaction (because the block itself is not a faithful copy of the conversation — only the points that still matter are).

The section titles are part of the contract: the next cycle parses this text back into a state, so both languages of the engine and the harness must agree on them. An example block is in `examples/state_block.md`.

The block opens with a header that warns the model the text below it is **state, not instructions** — nothing in the lists is a task to execute, and the live task is the user message that comes after the block. The block closes with a footer that says the same thing on the other side. Without those two guards the model treats the lists as a to-do and starts "doing" them.

## The eviction window

`Точные значения` is the section that decides whether the next turn can still do its job. The cap per section lives in `SECTION_CHAR_CAP` and is `1200` characters by default, with `Точные значения` getting a deliberately larger budget because it is the section that takes the damage. When the section is over budget, `_render_state` keeps both ends and drops the middle: the head of the list is what's been carried from the previous block, the tail is what the current cycle just produced. Anything in between is replaced by a `…[середина списка вырезана]…` marker. The user's next turn is expected to come from the tail of the list (freshest values); the head is the carried context. If a value the next turn needed was neither in the head nor the tail of the list, it is gone — and that is by design, because the model header explicitly says: when in doubt, re-read the value with a tool. The block is what to *start* with; the tools are what to *verify* with.

## How the block is carried forward

Two compaction cycles in a row are common: a session compresses, the user keeps working, the next turn pushes the context past the boundary again, and compression fires a second time. If the second cycle treated the previous block as just more text to summarise, the exact values from cycle 1 would die in cycle 2 — and that is exactly the failure I measured on the old engine (fresh values dropped from 50.7% to 12.0% across a second cycle). The fix:

- The previous block is **parsed**, not summarised. `_parse_sections` walks the eight section titles and pulls the lists back into a state dict. `_TITLE_TO_KEY` is the table that maps a Russian title to an internal key, and that table is the only place the two languages are tied together.
- The current cycle's new state (from the model or the fallback) is **merged** into the parsed previous state by `_merge_state`. New wins on conflicts (the current task is the live task, not the old one). Identifiers keep the fresh ones at the top and push the carried ones behind them; if the merged list is over the cap, the carried old ones drop off first.
- The auxiliary model is **never** asked to summarise the previous block. It only sees the middle of the conversation. That is the architectural rule that keeps exact values alive across cycles.

The trade-off: the carried section can grow stale. The contract is that the live task in the current `Задача` line is authoritative, and the `Проверить после сжатия` section is the place to list anything the next turn should re-read with a tool.

## What happens when the model is not available

Network down, provider rate-limited, key revoked, or the model simply answers with prose instead of JSON — `_ask_state` raises, the exception is logged, and `compress()` falls through to `_fallback_state`. The fallback builds a state dict directly from the messages in the middle: it scans tool calls and tool results for exact values, takes the last user message as the task, marks the rest as "open". The block is still rendered, still marked, still carried. The price is no narrative: no "decisions", no "constraints" — only what the deterministic scan could find. The journal records `state_src: детерминированно` so the operator can see when this path was taken.

The deterministic path also keeps an offline invariant for the tests: `compress()` returns the **same object** it was given when there is nothing to compress, so the host can call it unconditionally and short-circuit on identity. That is the test `test_compress_noop_returns_the_same_object`.

## Quick start

```bash
# 1. Put the engine where the host looks for context engines, and select it
cp autocompact.py ~/.hermes/plugins/autocompact/__init__.py
hermes config set context.engine autocompact

# 2. Set the knobs (see examples/engine_config.yaml)
hermes config set compression.threshold_tokens 250000
hermes config set compression.autocompact_preflight_ratio 0.6
hermes config set compression.autocompact_tail_tokens 25000
```

The defaults in `examples/engine_config.yaml` are the ones I run with. Lower `autocompact_preflight_ratio` (e.g. `0.5`) compresses earlier and saves more tokens per cycle at the cost of more frequent compactions; higher (e.g. `0.7`) lets sessions ride longer and compresses harder when they finally do. `autocompact_tail_tokens` is the freshness knob — I keep it at `25000` so the last turn of the user is always inside the tail and survives verbatim.

## Configuration

| Key (under `compression:`) | Default | Meaning |
|---|---|---|
| `threshold_tokens` | `250000` | Hard trigger: at the wall, compact regardless |
| `autocompact_preflight_ratio` | `0.6` | Share of the threshold at which a task boundary may trigger compaction |
| `autocompact_target_ratio` | `0.45` | What a compaction aims for |
| `autocompact_tail_tokens` | `25000` | Fresh work kept verbatim, measured in tokens |

All four are read at engine construction (`_cfg_num` falls back to the defaults shown above when the key is missing), and they can be set independently. The thresholds are deliberately round numbers; what matters is the *ratio* between them, not the absolute values. A 200K threshold and a 90K tail behaves the same as a 250K threshold and a 113K tail — both keep roughly 45% of the ceiling as fresh tail.

## Acceptance: judging by continuation

`resume_eval.py` runs on a **copy** of the state database (the live one is refused) and measures three things:

- **A. Exact values.** The part a compaction cuts out is scanned mechanically for values that cannot be re-derived — paths, session ids, hashes, addresses, unit and file names, commands, quantities. Search-result noise is discarded. The **fresh edge** of that window is scored separately, because that is what the next turn works from.
- **B. Session life and anti-ratchet.** Cycle 1 compacts the first half; the second half then arrives (work continued) and cycle 2 fires. Freed share and value survival must not collapse, and the context must hold **exactly one** state block — never a stack of them.
- **C. Live quiz (`--live`).** A model writes questions about the cut-out part with gold answers; a fresh session that sees **only the compacted context** answers them; a third model grades against the gold answers.

```bash
cp ~/.hermes/state.db /tmp/state_copy.db          # the live database is never read
PY=$(ls -d ~/.hermes/tools/python-*/bin/python3 | head -1)
HERMES_HOME="$HOME/.hermes" "$PY" -I resume_eval.py \
  --db /tmp/state_copy.db --session <session_id> --cycles 2 --live
```

The script prints one line per cycle with the token counts, the freed percentage, the fresh-value survival percentage, the carried-value survival percentage, and the structural invariants. At the end it prints a `bars` table — one row per acceptance criterion, marked with `✓` / `✗` / `·` (the last means "informational, not a gate"). The script exits non-zero if any *gated* bar failed, so it can be wired into a CI step on changes to the engine.

## Measured results

One real session (901 messages, 405,318 tokens): after compaction 59 messages, 31,527 tokens — 92.2% freed, a 13,090-character state block, no structural errors.

On a copy of a 4,000-message session, two cycles with work continuing between them:

| Cycle | Tokens before | Tokens after | Freed | Fresh exact values kept | Carried from the previous block |
|---|---|---|---|---|---|
| 1 | 783,419 | 40,329 | 94.9% | 95.4% of 65 | — |
| 2 | 995,896 | 34,363 | 96.5% | 74.2% of 93 | 95.4% of 65 |

One state block per cycle, zero orphan tool results, and the live quiz scored 8/8 after cycle 1 and 8/8 after cycle 2. The offline probes in `tests/` run in a second and cover the parts that decide what survives: section round-trip, carry-over, the eviction window, the no-op contract, the model-failure path.

The numbers that matter most to me are the fresh-value survival percentages (`survival_fresh_pct`) and the carried-value survival (`carry_pct`). The first says "can the next turn still do its job"; the second says "did the second cycle destroy what the first cycle saved". Both have to stay above their thresholds — 70% and 80% respectively — or the engine is just releasing tokens, not preserving work.

## Limitations

- The engine is a plugin for the Hermes agent runtime and imports from it (`agent.context_engine`, `agent.model_metadata`, `agent.compression_marker`, `agent.auxiliary_client`); it is not a standalone library. The tests stub those four modules.
- The state block is written in Russian, and its section titles are the interface between cycles. Porting it means porting `_TITLE_TO_KEY`, `_render_state` and the harness together.
- Values from deep in the cut-out part are **not** in the block by design — the block keeps a bounded window, and the header says so: the old material is meant to be re-read with a session search rather than trusted from memory.
- Quality is capped by the compaction model: a model that answers with prose instead of JSON drops the engine onto its deterministic path, which keeps structure but loses the narrative.
- `--live` spends real model calls on the quiz; it is a release gate, not a per-compaction check.

A few more I learned the hard way and keep in mind when changing the engine:

- The token estimator (`estimate_messages_tokens_rough`) is rough by name and by design. A four-character-per-token average over a whole session drifts; the wall trigger fires a few thousand tokens before the *real* ceiling, which is fine, but it is the reason the safety net is `threshold_tokens` and not a more aggressive number.
- The carry-over is bounded by `SECTION_CHAR_CAP` for the identifiers section. If a session genuinely needs more than ~14 000 characters of exact values, the carried values get evicted and the next cycle starts losing context. The mitigation is to keep long sessions under the ceiling, not to raise the cap — the cap is also the load the next cycle has to re-process.
- The journal (`data/autocompact_decisions.jsonl`) is append-only and includes `block_sha256`. It is the only place the operator can see *which* block came out of *which* compaction. Disabling it with `AUTOCOMPACT_JOURNAL=off` is meant for the acceptance harness, not for production.

## Structure

```
├── autocompact.py              # the engine (Hermes context-engine plugin)
├── resume_eval.py              # acceptance: exact values, two cycles, live quiz
├── README.md                   # English documentation
├── README.ru.md                # Russian documentation
├── tests/
│   └── test_state_sections.py  # offline tests: sections, carry-over, invariants
└── examples/
    ├── engine_config.yaml      # the config keys and their defaults
    └── state_block.md          # a rendered state block
```

## License

MIT License - see the LICENSE file in the repository for details.