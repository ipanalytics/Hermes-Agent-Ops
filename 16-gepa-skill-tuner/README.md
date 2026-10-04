# 16 — gepa-skill-tuner

_Русская версия: [README.ru.md](README.ru.md)_

**The text my agent works from — its system prompt, its cron prompt, its SKILL.md — decides how well it does the job. This folder rewrites that text against tasks with known correct answers and hands me a diff I can review before anything ships.**

A few words for anyone new to the setup. **Hermes** is the personal AI agent I keep at home: it lives on a server of mine, runs on a schedule (a *scheduled job* or *cron job* — a script that fires on a timer, like every hour), handles its own routines, and writes the scripts it needs. This folder is one of those scripts — it does not change a running agent in place, it changes *the text the agent is built on*: the prompt a scheduled task is given, or one section of a `SKILL.md` (the instruction file Hermes reads before acting on a topic).

A few more terms before I get to the script itself, because they appear below and a wrong guess about them wastes a lot of compute. An **LLM** (*Large Language Model*) is the AI the prompt is sent to. A **rollout** is one paid run of the prompt against one task. A **token** is roughly a word or a fragment of a word — the unit the bill is counted in. A **metric** is the rule that says whether the model's answer was right or wrong. The **train/val split** is how I keep my numbers honest: part of the data the optimizer learns on, part kept aside so I can check the optimizer never saw it. **GRPO** is a competing reflection-based RL method that GEPA is usually compared to; it reads traces too, but through a learned scalar head rather than free-form prose. **MoE** (*Mixture of Experts*) is the architecture behind most hosted task models — many specialised sub-models route different inputs, and that routing is what makes duplicate training rows especially punishing (arXiv 2609.11917).

A *prompt* is the text I give the model; *SKILL.md* is the instruction file my agent reads before it acts. Both are plain text, both are cheap to edit, and both usually sit untested — I edit them, restart the agent, and hope. This module replaces the hoping with a number.

> GEPA (*Reflective Prompt Evolution Can Outperform Reinforcement Learning*, arXiv 2507.19457,
> ICLR 2026 Oral, MIT) improves text parameters by letting an LLM **read full execution
> traces** and reflect in natural language, instead of collapsing a rollout into one scalar
> reward. Reported results: up to 35× fewer rollouts than GRPO, +6…20% over it, and a
> 55% → 82% on a coding agent via auto-learned skills. For an agent whose shipped knowledge
> *is* text (system prompt, cron prompt, skill), that maps directly onto the artifact.

A *rollout* here is one paid run of the prompt on one task, and a *token* is roughly a word or
part of a word — the unit the model's API bills by. So "fewer rollouts" simply means a cheaper
search for a better prompt.

## Why it exists

I edit prompts, restart the agent, and hope. Hope is not a metric. The set of complaints I got from a single router prompt over six weeks looked like this, with the same three sentences repeating in slightly different forms: "it picked the wrong skill", "it spent too many tokens before committing", "it called the wrong tool first". I could keep fixing the wording by hand, but I had no way to know whether my fix was better than the version it replaced, or whether the next tweak was undoing the last one. Without a number, every edit is a guess and every roll-back is a superstition.

GEPA exists because that question is not new. The paper's claim is not that text optimization is a new idea — it is that letting an LLM **read the full execution trace** and reflect on it in natural language buys a lot more than collapsing a rollout into one scalar reward the way classic reinforcement learning does. The reported numbers are unusually large for this kind of paper: up to **35× fewer rollouts** than GRPO, **+6…20%** over it, and a **55% → 82%** jump on a coding agent through auto-learned skills. For an agent whose shipped knowledge *is* text — system prompt, cron prompt, `SKILL.md` — that maps directly onto the artifact. The unit I tune is the same unit the agent ships.

## What I get here

- `tuner.py` — one command: a seed prompt file, or one section of a `SKILL.md` (`--skill ~/.hermes/skills/foo/SKILL.md --section "## Rules"`), plus a JSONL task set, plus a metric → a JSON report with every candidate's validation score and a **unified diff** I can read like code.
- `tests/test_dedupe.py` — the dedupe step under test (collapsing repeated inputs, label conflicts, order stability); runs with plain `python3` or `pytest`.
- `examples/shell-safety/` — a 30-row labelled task set from module 15, ready to run as a smoke test.

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

The metric is either exact/contains match on the `answer` field of each JSONL row, or my own `evaluate(data, response) -> (score, feedback)` module. I bind the API key the same way the agent does (`OPENROUTER_API_KEY` in the environment or `~/.hermes/.env`); the script does not store keys itself.

I feed it three things: the text to improve, a set of tasks where I know the correct answer for each one, and a metric. The tool tries rewritten versions of my text, scores each against the held-out part of the data, and at the end I get a diff — the changed lines, like a code change — plus the score of every version it tried. If nothing beats the seed, the run reports that and writes nothing.

## Duplicates are the first bug in a task set, not a detail

*tuner.py* collapses repeated inputs before the train/val split (whitespace collapsed, case folded). The *train/val split* is how I keep myself honest: part of the tasks is shown to the optimizer while it works, the rest is kept aside and scored only at the end — a prompt that only memorised the first part fails the second. If the same request appears in both parts (a duplicate), the score lies. Skipping the dedupe step does three separate kinds of damage:

- **Leakage.** The split is a slice of the file, so a repeated request gets optimised on *and* scored. The validation number rises while the prompt does not improve — the score I would write a `SKILL.md` change on is a lie.
- **Memorisation.** A reflective optimizer reads traces and rewrites instructions in prose; shown the same row five times it explains *that row* instead of the rule behind it. Repeated data punishes MoE models hardest (see *MoE models overfit more to repeated data*, arXiv 2609.11917) — and that is exactly what most hosted task models are.
- **Cost.** Every copy is another paid rollout against the budget I declared up front. A 124-row raw set becoming a 70-row deduplicated set is 54 paid rollouts I do not have to pay for.

I measured this on a real routing set (logged agent requests → skill name, the case this
module was built for; "routing" means deciding which skill handles which request):

| | rows | after split | train ∩ val input overlap | conflicting labels |
|---|---|---|---|---|
| raw | 124 | 86 / 38 | 1 | 30 groups |
| `tuner.py` (dedupe on) | 70 | 49 / 21 | 0 | reported per group |

My run prints what it dropped and which conflicts it resolved (`kept 'home-infra-ops' out of {'home-infra-ops': 1, 'personal-health-pipeline': 1}`) and carries the whole thing in the report under `dataset`. Majority label wins a group; ties keep the first occurrence. I surface conflicts, never average them away silently — a set where the same request has four different "correct" answers is a labelling problem upstream, and no prompt can fix it. `--keep-duplicates` runs the old behaviour when I want to show the difference.

## Rules

1. **The dataset is cleaned before anything is measured.** I collapse duplicate inputs and report label conflicts (see the section above); without that the split leaks and the optimizer learns the repeat instead of the rule.
2. **I declare the cost before I start.** `--max-metric-calls` is the whole budget, counted in paid runs; a run of 60 calls against a cheap model is seconds and cents.
3. **A held-out split, always.** The score I report is validation — the part the optimizer never saw — not the tasks it learned from.
4. **No fake improvements.** If nothing beats the seed, the tool says so (`No prompt change survived validation`) and writes no diff. My shell-safety example does exactly that with a strong task model — the seed prompt is already at the ceiling, so there is nothing to harvest. I pick a task where the *prompt* is the bottleneck.
5. **I review it like a code change.** The output is a diff plus the score per candidate; a regression in the diff is visible, and the file is only touched with `--write`.

## Recipe: a routing prompt from logged traffic

The cheap, repeatable loop I wrote this module for — it turns the agent's own history into a better prompt:

1. **Harvest.** I pull (request → skill/tool actually used) pairs from the agent's session store — real requests, including the messy dictated ones, not hand-written examples.
2. **Label.** I keep only rows where the outcome is verifiable (the skill really ran, the task succeeded) and drop the ambiguous ones instead of guessing: 30 of 70 unique rows in my set were labelled more than one way, and rows like that teach the tuner nothing.
3. **Dedupe** (automatic, above) and check the printed conflict report before spending a single rollout.
4. **Tune with a small budget.** `--max-metric-calls 20` on my 70 unique rows was one iteration in 8 seconds; I raise it only once a candidate moves the held-out score.
5. **I ship the diff, not the report.** The winning prompt goes back into the router as a reviewed change (`--write` or a patch), and afterwards I re-run the same holdout to confirm the gain held on data the optimizer never saw.

## Where it belongs in my agent deployment

I run it against surfaces with a real, repeatable failure rate and a cheap label:

- a **cron prompt** (a scheduled job that runs the agent on its own) that keeps producing items the operator rejects,
- a **skill section** whose checklist `hermes verify` can score,
- a **routing/dispatch prompt** — the one that decides which skill handles which request — scored against logged (request → correct tool/skill) pairs.

I do not point it at a task the model already solves; the run will report no change.

## Safety notes

- I install into an isolated virtualenv under `$HERMES_HOME/venvs/` (a virtualenv is a separate Python sandbox, so an install can't touch the agent's own packages). `litellm` 1.82.7/1.82.8 were flagged malicious on PyPI; my requirement file pins away from them, and Hermes' own package scanner warns before an install.
- A tuned prompt is still a prompt: any candidate that will execute commands goes through module 15's `bash_guard` before I trust it.