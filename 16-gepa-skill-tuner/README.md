# 16 — gepa-skill-tuner

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

## The discipline that keeps this honest

1. **Cost is declared before you start.** `--max-metric-calls` is the whole budget; a run of
   60 calls against a cheap model is seconds and cents.
2. **A held-out split, always.** The reported score is validation, not the training minibatch.
3. **No fake improvements.** If nothing beats the seed, the tool says so
   (`No prompt change survived validation`) and writes no diff. Our shell-safety example does
   exactly that with a strong task model — the seed prompt is already at the ceiling, so there
   is nothing to harvest. Pick a task where the *prompt* is the bottleneck.
4. **Review like a code change.** The output is a diff plus the score per candidate; a
   regression in the diff is visible, and the file is only touched with `--write`.

## Where it belongs in an agent deployment

Run it against surfaces with a real, repeatable failure rate and a cheap label:

- a **cron prompt** that keeps producing items the operator rejects,
- a **skill section** whose checklist `hermes verify` can score,
- a **routing/dispatch prompt** scored against logged (request → correct tool/skill) pairs.

Do **not** point it at a task your model already solves — that is the most common way to burn
an afternoon and call the null result a win.

## Safety notes

- Install into an isolated virtualenv under `$HERMES_HOME/venvs/`. `litellm` 1.82.7/1.82.8
  were flagged malicious on PyPI; the requirement file pins away from them, and Hermes'
  own package scanner warns before an install.
- A tuned prompt is still a prompt: run any candidate that will execute commands through
  module 15's `bash_guard` before trusting it.
