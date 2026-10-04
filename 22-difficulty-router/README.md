# 22 — difficulty-router

_Русская версия: [README.ru.md](README.ru.md)_

![License](https://img.shields.io/badge/license-Apache%202.0-blue)
![Status](https://img.shields.io/badge/status-active-success)
![Runtime](https://img.shields.io/badge/runtime-python%203.10%2B-informational)

**Route every scheduled job to a model tier by measured difficulty — and refuse the repin that makes mechanical work more expensive.**

Hermes is the home AI agent I run on my own server. It does not just answer chat messages; a large part of its day is jobs that fire on their own: a morning digest, a price watch, an hourly check, an end-of-day cleanup. Each of those jobs is a small scheduled task — what the scheduler calls a "cron job". A cron job in Hermes is basically: "run this prompt against an AI model at this time, then deliver whatever it prints to a chat topic". Every such job runs against a *model*, the AI doing the thinking, and every model is paid for by the *token* — a token is roughly one word or one piece of a word, and the bill at the end of the month is tokens times a price that depends on which model answered. Behind the model sits a *provider* — the company or gateway that actually serves the answer when I send a request.

Choosing which model a scheduled job uses is called *pinning* — the job gets attached to a specific name. "Repinning" is when the name changes. Picking the right name once and forgetting it is the mistake this folder exists to stop.

> Two mistakes cost me money in opposite directions: a reasoning-heavy job on the cheapest model fails
> and retries, paying twice for a worse answer; a mechanical job on a strong model pays ten times the
> price for identical output. Neither is visible in a job list, and both are visible in a usage
> ledger. This tool ends the guessing: it reads what each scheduled job actually did, decides whether
> the job needs a smart expensive model or a cheap one is enough, and proposes the switch — with a
> hard rule that exists because I broke it once. A *repin* below is simply swapping the model a
> scheduled job runs on.

## Why it exists

My job list said nothing about cost; my usage ledger said everything. But reading it by hand ended
the same way twice. Once I left a reasoning-heavy job on the cheapest model and paid for the savings
in retries; once I moved mechanical jobs to a model that read as "better value" and paid more for
the same output. The router exists to make that reading automatic: it computes per-job features from
the *audit log* (one JSON Lines record per model call, with timestamp, job id, prompt tokens, completion tokens, and any error), classifies the job, and recommends a tier — and it refuses the repin that made me
lose money the second time.

The rule that came from that mistake: I repinned three mechanical mail jobs from an older cheap
model to a newer one — "newer" read as "better value" — and their cost per token went up by a factor
of 2.3 to 3.3 while the output did not change. The direction of the price was never checked against
the direction of the work. Hence the refusal: when a job is classified mechanical and the target
tier is dearer per token than the current model, the router reports the recommendation and refuses
to apply it. Newer is not cheaper, and a mechanical job cannot benefit from a better reasoner.

The mirror case is the useful one: a job whose p90 output runs to thousands of tokens, or whose error
rate is high, is being served by a cheap model and paying for it in retries. That is the repin worth
doing, and the *rollback file* the tool writes makes it a two-command experiment: apply, watch a day,
revert from JSON.

## How it works

| Step | What happens |
|---|---|
| read | `--jobs`, `--audit`, `--prices` (jobs file, audit log, price+tier map) |
| score | per-job features from the last `--window-days` (default 14): runs, median prompt, median and p90 completion tokens, error rate |
| classify | `plain` / `mid` / `reasoning` by configured bands |
| repin | `--apply` runs a command template per job and writes `routing_rollback.json` |
| refusal | a repin that raises the price per token of a mechanical job is printed, not applied |

The tool reads the jobs file and the usage audit, computes the features, prints a verdict and a
proposed move per job:

```bash
python3 difficulty_router.py --jobs jobs.json --audit usage_audit.jsonl --prices examples/prices.json
python3 difficulty_router.py ... --apply      # repin + write a rollback file
```

The three tiers correspond to three real jobs my scheduler runs:

- `plain` — short fixed-text work, alerts and reminders. Median answer under ~400 tokens, error rate near zero. Should never cost more than the cheapest available model.
- `mid` — the default for jobs without enough runs to classify (under `min_runs`, default 3), and for jobs that do not look mechanical or reasoning. Honest, not clever.
- `reasoning` — long outputs (p90 over ~3000 tokens) or error rate over 20%. The cheap model here is paying for itself in retries.

The defaults live in `examples/prices.json` and can be tightened or loosened per deployment. The
hard rule the tool never overrides: jobs with too few runs are left alone — a classifier fed three
samples is a random number generator with a table around it.

## Quick start

```bash
python3 difficulty_router.py --jobs jobs.json --audit usage_audit.jsonl --prices examples/prices.json
```

I run it without `--apply` first, read the proposed list, and only then apply — with the rollback
file it writes at hand. `--apply` takes the same command template the audit log was already using to
create them (the default is `hermes cron edit {job_id} --model {model} --provider {provider}`), so
repins look exactly like the ones I would run by hand. The rollback file, `routing_rollback.json`,
sits next to the script: every previous pin, one line per job, so a single `hermes cron edit` per
job brings everything back.

## Outputs

- per job: the measured features, the verdict (`plain` / `mid` / `reasoning`) and the proposed move;
- the refusal line for any repin that would raise the per-token price of a mechanical job, with a
  short reason that names the direction ("already mechanical, target is dearer" / "classified
  reasoning, target is cheaper" / "mid");
- with `--apply`: the applied command template per job and `routing_rollback.json` for the way back.

The example price map in this folder pairs three tiers with three representative models and a fourth
legacy model (`cheap-old`) — the prices in it are USD per million tokens for input and output, and the
tiers are intentionally generic. Anyone can map them to their own providers: replace the `model` and
`provider` strings, keep the bands. The bands are the part that matters — what counts as a short
completion that counts as mechanical, the p90 that counts as reasoning, and the error rate that
overrides a short output.

## When I run it

I run the router on a weekly cadence, after a fresh export of the audit log. Three things go in front
of the verdict before I trust any of it: how many days the audit log covers (under `window_days`
there is not enough signal to classify anything), whether the audit log is complete (a missing day
silently reads as "zero errors"), and which jobs in the jobs file have no entry in the audit at all
(new jobs, jobs disabled since the last export, jobs whose names changed). A refusal that lists
every job as "insufficient data" is almost always one of these three, not the router failing.

## Limitations

- Output length is a proxy for difficulty, and it is wrong sometimes: a long mechanical report and a
  short hard question both exist.
- Error rate mixes difficulty with the quality of the surrounding script; a broken input pipeline
  looks like a difficult job.
- Prices are per token, so the tool compares directions, not total spend; I pair it with
  `19-cost-governance` for the per-task number.
- The tool is offline — it does not call any model. The audit log is read, never rewritten.

## Directory structure

```
22-difficulty-router/
├── difficulty_router.py     # the router: score, verdict, refusal, apply
├── examples/prices.json     # tier→model map + bands
└── tests/test_router.py     # verdicts and the refusal case
```

## Related

- **19-cost-governance** — the per-outcome cost number this router optimizes against.
- **17-model-slot-bakeoff** — the one-off measurement behind a slot's model pinning; this module
  keeps the same question running continuously over every scheduled job.

## License

Apache 2.0 — see the repository LICENSE.

## Disclaimer

`--apply` edits live schedules. I run without it first, read the proposed list, then apply with the
rollback file at hand.