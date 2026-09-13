# 22 — difficulty-router

_Русская версия: [README.ru.md](README.ru.md)_

![License](https://img.shields.io/badge/license-Apache%202.0-blue)
![Status](https://img.shields.io/badge/status-active-success)
![Runtime](https://img.shields.io/badge/runtime-python%203.10%2B-informational)

**Route scheduled jobs by measured difficulty — and refuse the repin that makes mechanical work more
expensive.**

> Two mistakes cost money in opposite directions: a reasoning-heavy job on the cheapest model fails
> and retries, paying twice for a worse answer; a mechanical job on a strong model pays ten times the
> price for identical output. Both are invisible in a job list, and both are visible in a usage
> ledger. This tool scores each job from what it actually did and recommends a tier — with a hard rule
> that exists because I broke it once.

## Overview

| Step | What happens |
|---|---|
| features | per job: runs, median and p90 completion tokens, median prompt, error rate |
| verdict | `plain` (short, reliable output), `mid`, `reasoning` (long or error-heavy) |
| repin | `--apply` runs a command template per job and writes `routing_rollback.json` |
| refusal | a repin that raises the price per token of a mechanical job is printed, not applied |

## The rule that came from a real mistake

I repinned three mechanical mail jobs from an older cheap model to a newer one — "newer" read as
"better value" — and their cost per token went up by a factor of 2.3 to 3.3 while the output did not
change. The direction of the price was never checked against the direction of the work. Hence the
refusal: when a job is classified mechanical and the target tier is dearer per token than the current
model, the router reports the recommendation and refuses to apply it. Newer is not cheaper, and a
mechanical job cannot benefit from a better reasoner.

The mirror case is the useful one: a job whose p90 output runs to thousands of tokens, or whose error
rate is high, is being served by a cheap model and paying for it in retries. That is the repin worth
doing, and the rollback file makes it a two-command experiment.

## How it works

```bash
python3 difficulty_router.py --jobs jobs.json --audit usage_audit.jsonl --prices examples/prices.json
python3 difficulty_router.py ... --apply      # repin + routing_rollback.json
```

```
mail-brief        plain     медиана ответа 210 токенов, ошибок 0%    plain-flash → plain-flash
release-digest    reasoning p90 ответа 8 400 токенов, ошибок 0%      plain-flash → reasoning
inbox-triage      plain     медиана ответа 180 токенов, ошибок 0%    cheap-old   → plain-flash  ❌ отказ: механика не должна дорожать
```

Bands are configuration, not constants: minimum runs before a job is classified at all, the median
completion that counts as mechanical, the p90 that counts as reasoning, and the error rate that
overrides a short output. Jobs with too few runs are left alone — a classifier fed three samples is a
random number generator with a table around it.

## Limitations

- Output length is a proxy for difficulty, and it is wrong sometimes: a long mechanical report and a
  short hard question both exist.
- Error rate mixes difficulty with the quality of the surrounding script; a broken input pipeline
  looks like a difficult job.
- Prices are per token, so the tool compares directions, not total spend; pair it with
  `19-cost-governance` for the per-task number.

## Directory structure

```
22-difficulty-router/
├── difficulty_router.py          # features, verdicts, refusal rule, rollback
├── examples/prices.json          # prices, tiers, bands
└── tests/test_router.py          # verdicts and the refusal case
```

## License

Apache 2.0 — see the repository LICENSE.

## Disclaimer

`--apply` edits live schedules. Run without it first, read the proposed list, then apply with the
rollback file at hand.
