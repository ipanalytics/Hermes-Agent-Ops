# 16 — gepa-skill-tuner

_Русская версия: [README.ru.md](README.ru.md)_

**Optimize the parameter you actually ship — the prompt or the SKILL.md — against a task set with ground truth.**

> GEPA (*Reflective Prompt Evolution Can Outperform Reinforcement Learning*, arXiv 2507.19457,
> ICLR 2026 Oral, MIT) improves text parameters by letting an LLM **read full execution
> traces** and reflect in natural language, instead of collapsing a rollout into one scalar
> reward. Reported results: up to 35× fewer rollouts than GRPO, +6…20% over it, and a
> 55% → 82% on a coding agent via auto-learned skills. For an agent whose shipped knowledge
> *is* text (system prompt, cron prompt, skill), that maps directly onto the artifact.

## What you get here

- `tuner.py` — one command: seed prompt (or one section of a SKILL.md) + JSONL task set +
  metric → JSON report with every candidate's validation score and a unified diff.
- `tests/test_dedupe.py` — the dedupe step under test (collapsing, label conflicts, order
  stability); runs with plain `python3` or `pytest`.
- `examples/shell-safety/` — the 30-row labelled task set from module 15, ready to run.

## How to use it

```bash
python3 -m venv --without-pip .venv && curl -sSL https://bootstrap.pypa.io/get-pip.py | .venv/bin/python
.venv/bin/pip install -r requirements.txt

# plain prompt file
.venv/bin/python tuner.py --prompt-file seed_prompt.txt --dataset tasks.jsonl --out report.json

# one section of a skill, custom metric, then write the winner back
.venv/bin/python tuner.py --skill ~/.hermes/skills/foo/SKILL.md --section "## Rules" \
    --dataset tasks.jsonl --evaluator my_metric.py --max-metric-calls 150 --write
```

The metric is either exact/contains match on the `answer` field, or your own
`evaluate(data, response) -> (score, feedback)` module. Bind the API key the same way the
agent does (`OPENROUTER_API_KEY` in the environment or `~/.hermes/.env`).

## Duplicates are the first bug in a task set, not a detail

`tuner.py` collapses repeated inputs before the train/val split (whitespace collapsed, case
folded). Skipping this step does three separate kinds of damage:

- **Leakage.** The split is a slice of the file, so a repeated request gets optimised on *and*
  scored. The validation number rises while the prompt does not improve.
- **Memorisation.** A reflective optimizer reads traces and rewrites instructions in prose;
  shown the same row five times it explains *that row* instead of the rule behind it. Repeated
  data punishes mixture-of-experts models hardest (see *MoE models overfit more to repeated
  data*, arXiv 2609.11917) — which is exactly what most hosted task models are.
- **Cost.** Every copy is another paid rollout against the budget you declared up front.

Measured on a real routing set (logged agent requests → skill name, the case this module was
built for):

| | rows | after split | train ∩ val input overlap | conflicting labels |
|---|---|---|---|---|
| raw | 124 | 86 / 38 | 1 | 30 groups |
| `tuner.py` (dedupe on) | 70 | 49 / 21 | 0 | reported per group |

The run also prints what it dropped and which conflicts it resolved (`kept 'home-infra-ops'
out of {'home-infra-ops': 1, 'personal-health-pipeline': 1}`) and carries the whole thing in
the report under `dataset`. Majority label wins a group; ties keep the first occurrence.
Conflicts are surfaced, never averaged away silently — a set where the same request has four
different "correct" answers is a labelling problem upstream, and no prompt can fix it.
`--keep-duplicates` runs the old behaviour when you want to show the difference.

## Rules

1. **The dataset is cleaned before anything is measured.** Duplicate inputs are collapsed and
   label conflicts reported (see the section above); without that the split leaks and the
   optimizer learns the repeat instead of the rule.
2. **Cost is declared before you start.** `--max-metric-calls` is the whole budget; a run of
   60 calls against a cheap model is seconds and cents.
3. **A held-out split, always.** The reported score is validation, not the training minibatch.
4. **No fake improvements.** If nothing beats the seed, the tool says so
   (`No prompt change survived validation`) and writes no diff. Our shell-safety example does
   exactly that with a strong task model — the seed prompt is already at the ceiling, so there
   is nothing to harvest. Pick a task where the *prompt* is the bottleneck.
5. **Review like a code change.** The output is a diff plus the score per candidate; a
   regression in the diff is visible, and the file is only touched with `--write`.

## Recipe: a routing prompt from logged traffic

The cheap, repeatable loop this module was written for:

1. **Harvest.** Pull (request → skill/tool actually used) pairs from the agent's session store —
   real requests, including the messy dictated ones, not hand-written examples.
2. **Label.** Keep only rows where the outcome is verifiable (the skill really ran, the task
   succeeded). Drop the ambiguous ones instead of guessing: 30 of 70 unique rows in our set were
   labelled more than one way, and those rows teach the tuner nothing.
3. **Dedupe** (automatic, above) and check the printed conflict report before spending a single
   rollout.
4. **Tune with a small budget.** `--max-metric-calls 20` on 70 unique rows was one iteration in
   8 seconds; raise it only once a candidate moves the held-out score.
5. **Ship the diff, not the report.** The winning prompt goes back into the router as a
   reviewed change (`--write` or a patch), and the same holdout is re-run afterwards to confirm
   the gain held on data the optimizer never saw.

## Where it belongs in an agent deployment

Run it against surfaces with a real, repeatable failure rate and a cheap label:

- a **cron prompt** that keeps producing items the operator rejects,
- a **skill section** whose checklist `hermes verify` can score,
- a **routing/dispatch prompt** scored against logged (request → correct tool/skill) pairs.

Do not point it at a task the model already solves; the run will report no change.

## Safety notes

- Install into an isolated virtualenv under `$HERMES_HOME/venvs/`. `litellm` 1.82.7/1.82.8
  were flagged malicious on PyPI; the requirement file pins away from them, and Hermes'
  own package scanner warns before an install.
- A tuned prompt is still a prompt: run any candidate that will execute commands through
  module 15's `bash_guard` before trusting it.
