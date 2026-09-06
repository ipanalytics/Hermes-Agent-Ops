# 07 — fresh-prompt-linter

**The code-review bot for prompt hygiene: will your cron prompt survive a fresh session?**

> A scheduled agent job runs in a NEW session with ZERO chat context. Prompts written against
> history — "as I said earlier", "the file we discussed", "you know my preferences" — are the
> quiet killer of cron reliability. They don't crash; they *drift*, hallucinate, or stall asking
> a user who isn't there.

## What you get here

- `fresh_prompt_linter.py` — a runnable, deterministic heuristic checker (no LLM involved, costs nothing, safe for CI/gates).
- `README.md` — you are here.

## It catches

- **History references**: "as mentioned", "see above", "the file we discussed", "as you know" → those break in a fresh session.
- **Drifting time**: "today / yesterday / tomorrow" with no explicit date anchor in the prompt.
- **Interactive stalls**: "ask me", "please confirm", "shall I" → a headless job has nobody to answer and hangs forever.
- **Unresolved placeholders**: `<thing>`, `{{x}}`, `${x}` — the templating step was forgotten.
- **Missing output discipline**: no wording about how/whether to report.

## How to use it

```bash
python3 fresh_prompt_linter.py --prompt-file my_job.md
echo $?    # 0 = OK (warnings only), 1 = FAIL — block the deploy
```

Wire it as a gate: a scheduler job with a prompt that fails the linter never gets created.
We run every recurring prompt through it before shipping; it has flagged real bugs
("as mentioned above" in a job that had no "above").

## Honest limits

It is a heuristic, not a guarantee: a prompt can pass and still fail (missing world
knowledge), or fail and still work. Treat the verdict as a strong signal, not proof.

## Why this gets stars

Everybody ships cron prompts; almost nobody checks them for the fresh-session trap.
Deterministic, zero-cost, CI-able — and the failure class is universal.
