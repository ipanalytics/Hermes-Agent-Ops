# 35 — Context Compaction Engine

_Russian version: [README.ru.md](README.ru.md)_

![License](https://img.shields.io/github/license/ipanalytics/Hermes-Agent-Ops)
![Status](https://img.shields.io/badge/status-active-brightgreen)
![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue)

A context-compaction engine for Hermes Agent that replaces a long session with a **working state** — task, decisions, constraints, exact values, next step — instead of a summary of the conversation, plus the acceptance harness that judges a compaction by whether the task can still be finished afterwards.

## Why it was created

The engine I ran before this one removed stale tool results and never shortened the user or assistant text itself. Over one week of real sessions that design fails exactly where it matters: the text floor grows with every cycle (43K → 139K, 91K → 240K, 175K → 359K tokens in three long sessions), the share freed by a compaction falls each time it runs (89% → 55%, 76% → 20%, 63% → 8%), and one session sitting on a 200K window stopped compacting altogether — 0% freed, the context pinned at the ceiling.

Two things caused it, and both are design, not tuning:

1. **Compaction was triggered by volume.** "It crossed the threshold — cut it." Nothing decided whether the work in that window was still needed; a finished research pass and a half-written file looked the same.
2. **Nothing measured the result.** Freeing 90% of a context is easy if you are willing to lose the thread: drop the middle, keep the last few turns, and the number looks excellent. The only quality signal was how the session felt afterwards, noticed days later.

So this module is a replacement, not a patch: compact the *work*, and accept the compaction by *continuation*.

## What it does

1. **When to compact.** Not only at the wall. Compaction also fires on a task boundary: the user speaks again and the context is already past ~60% of the threshold, which means the previous pass of work is finished and stale (`should_compress_preflight`). The hard threshold stays as a safety net (`should_compress`).
2. **What to keep.** Instead of a narrative of the process, the working state: the task, decisions and why, constraints, **exact values verbatim** (paths, ids, keys, commands, error texts, numbers), what is done, what is open, the next step, and what to re-read after the compaction. A cheap auxiliary model writes it; the compaction never asks a decision model to write prose.
3. **How to continue.** The state block sits immediately after the protected head; the last `tail_tokens` of fresh work stay verbatim. The block is marked, so on the next cycle it is not cut again — it is **carried**: the previous block's sections are parsed and merged into the new one *without asking the model to re-summarise them*, which is where exact values used to die.
4. **How to verify.** Every compaction is journalled (`data/autocompact_decisions.jsonl`) and accepted by `resume_eval.py`: does a session that sees only the compacted context still know what it was doing.

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

The section titles are part of the contract: the next cycle parses this text back into a state, so both languages of the engine and the harness must agree on them. An example block is in `examples/state_block.md`.

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

## Configuration

| Key (under `compression:`) | Default | Meaning |
|---|---|---|
| `threshold_tokens` | `250000` | Hard trigger: at the wall, compact regardless |
| `autocompact_preflight_ratio` | `0.6` | Share of the threshold at which a task boundary may trigger compaction |
| `autocompact_target_ratio` | `0.45` | What a compaction aims for |
| `autocompact_tail_tokens` | `25000` | Fresh work kept verbatim, measured in tokens |

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

## Measured results

One real session (901 messages, 405,318 tokens): after compaction 59 messages, 31,527 tokens — 92.2% freed, a 13,090-character state block, no structural errors.

On a copy of a 4,000-message session, two cycles with work continuing between them:

| Cycle | Tokens before | Tokens after | Freed | Fresh exact values kept | Carried from the previous block |
|---|---|---|---|---|---|
| 1 | 783,419 | 40,329 | 94.9% | 95.4% of 65 | — |
| 2 | 995,896 | 34,363 | 96.5% | 74.2% of 93 | 95.4% of 65 |

One state block per cycle, zero orphan tool results, and the live quiz scored 8/8 after cycle 1 and 8/8 after cycle 2. The offline probes in `tests/` run in a second and cover the parts that decide what survives: section round-trip, carry-over, the eviction window, the no-op contract, the model-failure path.

## Limitations

- The engine is a plugin for the Hermes agent runtime and imports from it (`agent.context_engine`, `agent.model_metadata`, `agent.compression_marker`, `agent.auxiliary_client`); it is not a standalone library. The tests stub those four modules.
- The state block is written in Russian, and its section titles are the interface between cycles. Porting it means porting `_TITLE_TO_KEY`, `_render_state` and the harness together.
- Values from deep in the cut-out part are **not** in the block by design — the block keeps a bounded window, and the header says so: the old material is meant to be re-read with a session search rather than trusted from memory.
- Quality is capped by the compaction model: a model that answers with prose instead of JSON drops the engine onto its deterministic path, which keeps structure but loses the narrative.
- `--live` spends real model calls on the quiz; it is a release gate, not a per-compaction check.

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
