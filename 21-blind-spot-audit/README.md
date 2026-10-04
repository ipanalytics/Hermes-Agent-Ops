# 21 — blind-spot-audit

_Русская версия: [README.ru.md](README.ru.md)_

![License](https://img.shields.io/badge/license-Apache%202.0-blue)
![Status](https://img.shields.io/badge/status-active-success)
![Runtime](https://img.shields.io/badge/runtime-python%203.10%2B-informational)

**Automation accepts work by rules, and rules have a blind spot: the share of answers that look fine
to the checker and are wrong.**

I cannot see that share from inside the pipeline, and I cannot estimate it from the failures: the
missing work is in the successes, not in the errors. Before I measured it, "0 errors" in my log was a
statement about my checks, not about my output. The measurement is cheap: I draw a random sample of
recent outputs, hand them to a strong model with a rubric, and report the rate every week.

## What the words mean (for someone opening this repo for the first time)

Hermes is my home AI agent — a long-running assistant on my own server that does my routines
(digests, price and gear watches, health digests, monitoring its own failures) and writes
scripts for itself. An **automation pipeline** in this context is the chain of scheduled tasks
("cron jobs" — recurring jobs that the system runs on a timer) that produce digests, watches,
reports and other outputs without my sitting in front of them. A **gate** is one of the
automatic checks that accepts or rejects a piece of work (a check that says "this output has a
title and a price — pass", for example). A **blind spot** is the share of outputs that pass
the gate and are wrong — work that gets through, looks fine to the automated check, and is
still incorrect. The **failure log** is the file where the pipeline writes the jobs it
rejected; the **blind spot** is precisely what does *not* show up in that log. A **judge
model** is a separate, stronger model that reads sample outputs against a written rubric and
reports whether each one is fine, suspect or wrong; the rubric is the four-axis checklist
(invented fact, wrong requirement, internal contradiction, unsupported claim) the judge
applies. A **sample** here is a small, deterministic random slice of recent work — twelve
items drawn from the last week — and **deterministic** means rerunning the same command with
the same seed yields the same sample, so weekly reports are comparable. **Redaction** is the
filter that strips home directories, system paths, IP addresses, e-mail addresses, credential
strings and coordinates from the sample before it is shipped to the judge, so the
measurement does not itself become a leak.

## Why it exists

A rule-based check can only grade what its rules describe. Everything the rules do not cover
passes silently — and none of it reaches the failure log, because the failures my pipeline
caught are, by definition, not the blind spot. The gap grows exactly where it is hardest to
notice: recent work on verification measures the effect directly, and it turns out that the
blind spot of a cheap verifier grows as the verified model gets stronger, while an
expensive verifier escalates far more cases than the true error rate justifies (arXiv
2609.01345 reports escalation at 46% against a 39% error rate, and a blind spot rising from
roughly 0.12 to 0.55 across small-to-large students).

What that paper actually says, in plain terms: the cheap verifier that I was about to trust on
my own pipeline is the one whose blind spot is biggest in the regime where my agents already
live (small students, mid-cost work). The expensive verifier I might be tempted to swap in
does not have a smaller blind spot — it has a different failure mode, escalating far more
work than there are errors to catch, which is its own waste. There is no verifier side of
the pipeline that makes the blind spot go away; the only thing that makes it go away is
independent sampling plus a strong reader. That is what this folder is.

Two practical consequences, both implemented here:

- **Measure the successes.** Failure logs only contain what the checks caught.
- **Sample, do not exhaustive-check.** Judging every output with a strong model is exactly
  the cost I removed by automating. Twelve samples a week give a rate with a usable error
  bar; twelve thousand give a smaller one and no budget.

Why twelve: this is a rate of one event per trial, and a 95% Wilson interval on `k = 3 / n =
12` runs roughly 25% ± 13 percentage points — wide, but wide on purpose. The width is what
makes a single bad week hard to mistake for a trend; the cadence is what makes a trend
hard to miss across four consecutive weeks. I read the trend, not a single report.

## How it works

| File | Job |
|---|---|
| `sample_outputs.py` | draw N random outputs from the last D days, redact paths/addresses/credentials, write a sample + manifest |
| `judge_prompt.md` | the rubric: invented fact, wrong requirement, internal contradiction, unsupported claim |
| `examples/weekly_report.example.md` | what the judge's output looks like, including a week where the checks said 0 |
| `tests/test_sampler.py` | window selection, redaction, deterministic sampling |

`sample_outputs.py` walks a directory of job outputs, keeps files inside the window, draws a
deterministic sample for a given seed (so a rerun is comparable), redacts the local details
that have no bearing on quality, and writes a sample file plus a JSON manifest.

The sample file is deliberately boring. My weekly job reads it with the rubric and reports a
table plus three lines: the rate, the most expensive error found, and one recommended
change. The last line matters most — the audit exists to change something, not to score
anything.

Redaction covers home paths, absolute system paths, IP addresses, e-mail addresses,
credential-shaped strings and coordinates. It is a filter for accidental disclosure, not a
guarantee: I review a sample by hand the first time I point the tool at a new directory.

The four axes the judge scores, expanded:

- **Invented fact** — a number, name, date, price or quote presented as verified and not
  traceable to the excerpt the judge is reading. The axis that catches hallucinations: the
  output reads like it was sourced, but no source in the sample carries the claim. A digest
  with a specific rating for a specific product, where the excerpt has no rating, falls
  here.
- **Wrong requirement** — the output visibly misses the thing the job exists to produce.
  A digest with no download links, a report with no next step, a recipe with no quantities.
  The axis that catches "the model followed the style but missed the deliverable" — the
  shape is right, the substance is missing.
- **Internal contradiction** — two statements in the same output that cannot both be true.
  "All prices down this week" and "the third item rose 20%" without qualification. The axis
  that catches incoherence the format check cannot see.
- **Unsupported claim** — a conclusion stated with more certainty than the evidence in the
  excerpt. "This is the best release of the month" with no rating in the excerpt, no
  comparative numbers, no trace. The axis that catches overreach: the model has guessed,
  not measured.

A sample that fails none of these is `ok`; a sample that fails one but the failure is
ambiguous (the excerpt is thin, the judge says "I cannot verify") is `suspect`; a sample
where the failure is clear from the excerpt alone is `wrong`. The judge is told
explicitly: judge only what is in the excerpt; "I cannot verify this from the excerpt" is
`suspect`, not `wrong`; do not reward length or style. If the judge finds nothing in a
sample, it writes `ok` — a low rate is a valid and useful result, not a verdict on the
audit.

## Quick start

```bash
python3 sample_outputs.py --dir ~/.hermes/cron/output --days 7 --count 12 --out blindspot_sample.md
```

I hand the sample file and its manifest to my weekly judging job with `judge_prompt.md` as
the rubric, and file each report next to the previous weeks'.

The output of the script is two files: the Markdown sample (`blindspot_sample.md`) with one
section per picked output, each section redacted and trimmed to `--max-chars` (default 1200)
so the judge model sees a uniform slice, and a JSON manifest with the same entries in
machine-readable form (job name, file name, mtime, excerpt). The manifest is the link
between the judge's table and the original output if I need to look back; the Markdown is what
the judge model actually reads.

## Outputs

- a weekly table of judged samples and the blind-spot rate itself — the number no log can
  produce;
- the most expensive error found in the sample, so the fix is aimed rather than abstract;
- one recommended change to the checks or the prompt — the line the whole audit exists for.

What I do with the weekly output, in order: read the rate against last week's; if it moved
more than the error bar, look at the "most expensive error" first; read the recommended
action and decide whether to ship it this week or queue it. The recommended action is what
the audit is for: a measurement that does not change anything is a measurement that did not
pay for itself.

## Limitations

- The judge is not ground truth. It catches what an attentive reader would catch; a shared
  blind spot between student and judge stays invisible.
- A rate from twelve samples is noisy: week-over-week movement under roughly ten points is
  noise for me, and I read the trend, not a single report.
- Redaction is pattern-based. Prompts and outputs that quote unusual identifiers will not
  be covered.

What this means in practice: when a week shows 25% and the previous week showed 30%, I
treat them as the same number; when three weeks in a row show a flat 15%, I treat that as
the real rate; when the trend reverses and three weeks show a sharp rise, I ship the
recommended change even before I trust the absolute number. The shape of the curve
matters; the latest point does not.

The shared-blind-spot caveat is the one I keep in mind: if the judge model I use is the
same family as the student model on the same outputs, certain failure modes will be
invisible to both — the precise pattern each model family hallucinates is partly the
family's signature. I run the judge on a different provider tier from the student for
that reason; it is not a guarantee, but it widens the angle.

## Directory structure

```
21-blind-spot-audit/
├── sample_outputs.py             # sample + redact + manifest
├── judge_prompt.md               # rubric for the judging model
├── examples/weekly_report.example.md
└── tests/test_sampler.py         # window, redaction, determinism
```

## How I run this in practice

The audit lives on a weekly cron. The cron runs `sample_outputs.py` against
`~/.hermes/cron/output`, hands the sample + manifest to a judge-model prompt with
`judge_prompt.md` as the rubric, and files the result next to the previous weeks' under
`~/.hermes/cron/output/_blindspot/<YYYY-MM-DD>.md`. I read it on Monday morning; if the
rate moved sharply or the recommended action is a one-liner, I ship it the same day.

I do **not** keep the sample files in the repo. The sample is as sensitive as the outputs
it came from (names, prices, equipment, addresses).

## Related

- **20-task-evals-and-autopsy** — the checks whose blind spot this module measures: there
  the work is evaluated, here the evaluator is graded.
- **07-fresh-prompt-linter** — one of the gates that accept work by rules and therefore
  need this measurement to know what they let through.

## License

Apache 2.0 — see the repository LICENSE.

## Disclaimer

The audit samples my own agent's output; the sample file is as sensitive as the outputs
it came from. I store it where the outputs live, not in a repository.