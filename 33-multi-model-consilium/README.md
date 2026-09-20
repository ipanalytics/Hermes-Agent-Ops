# 33 — multi-model-consilium

_Русская версия: [README.ru.md](README.ru.md)_

**An answer from one model is one point of failure. Make a second model attack it, then make the
first model answer the attack in writing.**

> Reviewing a decision with the same model that produced it barely moves the odds: it agrees with
> its own assumptions. A model from a different family does not share them, and the objections it
> raises are usually checkable — a missed rollback path, an unverified claim, a cost that was
> never counted. Forcing the author to either fix the plan or explain why the objection is wrong
> is what turns three cheap calls into a decision you can defend.

## What you get

- `consilium.py` — runs three stages against any OpenAI-compatible endpoint: proposal,
  adversarial review, synthesis. Writes the full transcript to disk.
- `examples/mail-migration/` — a question and the transcript of a real run (2 models, 25k tokens
  in, 15.7k out, 263 s).
- `tests/test_consilium.py` — 12 offline tests: stage order, prompt plumbing, truncation retry,
  token accounting, error paths. No network, no API key.

## The three stages

| Stage | Who | What is asked |
|---|---|---|
| 1. Proposal | model A | a concrete plan: steps, order, known risks, the check that proves each step worked |
| 2. Attack | model B | find concrete holes: wrong assumptions, missing edge cases, unverified claims, blast radius. Every objection must be checkable |
| 3. Synthesis | model A | answer the attack: what is accepted and how the plan changes, what is rejected and why, then the final plan as steps |

Each stage is recorded with its model, prompt and usage, so the bill and the reasoning are both
on record. Retries are counted as spent tokens, not ignored.

## How to use it

```bash
export OPENROUTER_API_KEY=...          # or any key for --base-url
python3 consilium.py \
  --question-file examples/mail-migration/question.md \
  --model-a vendor/fast-model \
  --model-b other/vendor-model \
  --max-tokens 900 \
  --out-dir ./consilium-out
```

The synthesis is printed to stdout, the transcript is written to `--out-dir`, and the token
counts go to stderr. `--base-url` and `--api-key-env` point the tool at any compatible gateway.

## Output

The transcript is markdown with the question, then the three stages in order:

```
# Consilium — author model vs reviewer model
_tokens: 25089 in / 15711 out, 262.8 s_

## Question
## 1. Plan (author) — `<author model>`
## 2. Attack (reviewer) — `<reviewer model>`
## 3. Final plan (author answers the attack) — `<author model>`
```

The recorded run used two cheap hosted models from different families; their names are
left out on purpose — identifiers change every few months, the pattern does not.

## Two behaviours worth knowing

- **A truncated stage is retried, not accepted.** If the endpoint stops a reply at the token
  limit, the call is repeated with a doubled limit. If it still truncates, the text is returned
  with a visible marker rather than silently feeding half an answer into the next stage — a
  synthesis built on a truncated plan looks confident and is worthless.
- **The attack is not a vote.** Stage 3 is scored by whether each objection was answered, not by
  how many were raised. A review that finds nothing and says the plan is sound is a valid result.

## Limits

- Red teaming pays off where the criteria are checkable (migrations, budgets, contracts). On
  taste questions it adds a round without adding evidence.
- Two models can share a blind spot, especially if they are trained on similar data. Different
  families reduce this, they do not remove it.
- Three calls cost three times one call: keep the reviewer cheap and the author strong.
- The tool decides nothing on its own. It produces a record; the decision stays with you.
