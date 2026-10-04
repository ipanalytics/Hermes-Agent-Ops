# 33 — multi-model-consilium

_Russian version: [README.ru.md](README.ru.md)_

![License](https://img.shields.io/badge/license-MIT-blue)
![Status](https://img.shields.io/badge/status-active-success)
![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue)

**An answer from one model is one point of failure. Make a second model attack it, then make the
first model answer the attack in writing.**

This is the tool I reach for when a decision has checkable criteria — a migration, a budget, a
contract clause — and getting it wrong is expensive. I do not run it for taste questions; I do
not run it for things a calculator can check. The value of having a second model look at the
first model's plan is that the second model does not share the first model's assumptions, and the
objections it raises are usually concrete: a missed rollback path, an unverified claim, a cost
that was never counted.

> Reviewing a decision with the same model that produced it barely moves the odds: it agrees
> with its own assumptions. A model from a different family does not share them, and the
> objections it raises are usually checkable — a missed rollback path, an unverified claim, a
> cost that was never counted. Forcing the author to either fix the plan or explain why the
> objection is wrong is what turns three cheap calls into a decision I can defend.

The recorded run in `examples/mail-migration/` is a real example: should a small team move their
mail server from a rented VM to a home box behind a reverse SSH tunnel? The author wrote a
seven-step plan; the reviewer caught seven holes (source IP visibility lost through the tunnel,
ambiguous outbound path, unverified port 25 access, no monitoring, un-actionable rollback trigger,
split-brain during cutover, unverified home-link reliability); the author accepted all seven and
rewrote the plan around them. Two models, 25 089 input tokens, 15 711 output tokens, 262.8 s.

## What's in here

- `consilium.py` — runs three stages against any OpenAI-compatible endpoint: proposal,
  adversarial review, synthesis. Writes the full transcript to disk.
- `examples/mail-migration/` — a question and the transcript of a real run (2 models, 25k
  tokens in, 15.7k out, 263 s).
- `tests/test_consilium.py` — 12 offline tests: stage order, prompt plumbing, truncation retry,
  token accounting, error paths. No network, no API key.

`consilium.py` is the script I run. It is a single Python file, no dependencies beyond the
standard library and the `urllib` request I already had — meaning it runs on any Python 3.10+
install without a `pip install` step, which matters when I want to run it from cron or from a
container I do not control. The endpoint is configured: `--base-url` defaults to OpenRouter, but
the same script points at any OpenAI-compatible gateway (LM Studio, vLLM, Ollama's OpenAI
shim, a self-hosted llama.cpp) by changing one flag.

## The three stages

| Stage | Who | What is asked |
|---|---|---|
| 1. Proposal | model A | a concrete plan: steps, order, known risks, the check that proves each step worked |
| 2. Attack | model B | find concrete holes: wrong assumptions, missing edge cases, unverified claims, blast radius. Every objection must be checkable |
| 3. Synthesis | model A | answer the attack: what is accepted and how the plan changes, what is rejected and why, then the final plan as steps |

The order matters. The author has to commit to a plan before the reviewer sees it — not after.
If the author knew the reviewer's questions in advance, the author would just write a plan that
anticipates them, and the review would be theatre. Stage 3 is the author's reply to the attack,
in writing, with each objection marked accepted or rejected. A rejected objection has to explain
why it is wrong, not why it is inconvenient.

Each stage is recorded with its model, prompt and usage, so the bill and the reasoning are both
on record. Retries are counted as spent tokens, not ignored. The transcript is markdown, so it
reads naturally and diffs cleanly when I want to compare two runs of the same question.

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

The question can come from `--question-file` (I use this for anything longer than two lines)
or from `--question` (I use this for short one-liners). The synthesis prints to stdout, the
transcript writes to `--out-dir`, and the token counts go to stderr. `--base-url` and
`--api-key-env` point the tool at any compatible gateway. `--max-tokens` is the per-call budget;
the script raises it automatically if a reply comes back truncated.

The model identifiers are `vendor/model-name` strings — the format OpenRouter and most
compatible gateways expect. I keep them in shell variables in the cron entry so I can swap a
vendor without touching the script.

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

The token line at the top is what I check first. A 25k/16k transcript is in the normal range for
a question like the mail migration; a question with more context can run to 100k in, but I
keep questions short so the whole transcript fits in one screen. The recorded run used two
cheap hosted models from different families; their names are left out on purpose — identifiers
change every few months, the pattern does not.

## Two behaviours worth knowing

- **A truncated stage is retried, not accepted.** If the endpoint stops a reply at the token
  limit, the call is repeated with a doubled limit. If it still truncates, the text is
  returned with a visible marker rather than silently feeding half an answer into the next
  stage — a synthesis built on a truncated plan looks confident and is worthless. The retry
  bills tokens, not paper over them; the first attempt is counted as spent.
- **The attack is not a vote.** Stage 3 is scored by whether each objection was answered, not
  by how many were raised. A review that finds nothing and says the plan is sound is a valid
  result. Two objections accepted and addressed is better than seven objections raised and
  dismissed.

The unit tests in `tests/test_consilium.py` cover these two and nine more — the order of
stages, that the attack actually sees the plan, that retries really retry, that an empty
reply surfaces as an error rather than a silent empty string, that a network failure is
retried and then surfaced, that the transcript has all three sections and the question, that
the slug (filename) is filesystem-safe, and that `main()` writes the file. The suite is
`12/12 passed`, runs without the network, and takes a couple of seconds.

## Limits

- Red teaming pays off where the criteria are checkable (migrations, budgets, contracts). On
  taste questions it adds a round without adding evidence. I do not run it for "which font
  should I use" or "rewrite this paragraph" — the reviewer adds a round of cost without
  changing my odds.
- Two models can share a blind spot, especially if they are trained on similar data. Different
  families reduce this, they do not remove it. If I am checking something the entire field is
  bad at, the second model will not catch it.
- Three calls cost three times one call: keep the reviewer cheap and the author strong. The
  author is the one that has to synthesise; the reviewer is the one that has to be hostile.
  Picking both from the most expensive tier is a waste of money.
- The tool decides nothing on its own. It produces a record; the decision is mine. The
  synthesis is a draft plan; I am the one who reads the objections and decides which to take
  seriously.

The 25k/16k token run in `examples/mail-migration/` is the canonical example. Read the
transcript, see what stage 2 caught that stage 1 missed, and that is what the tool does. The
real numbers on a fresh question will be different, but the shape of the interaction — author
proposes, reviewer attacks, author answers in writing — is the part I keep coming back to.