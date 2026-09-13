# 21 — blind-spot-audit

_Русская версия: [README.ru.md](README.ru.md)_

![License](https://img.shields.io/badge/license-Apache%202.0-blue)
![Status](https://img.shields.io/badge/status-active-success)
![Runtime](https://img.shields.io/badge/runtime-python%203.10%2B-informational)

**Automation accepts work by rules, and rules have a blind spot: the share of answers that look fine
to the checker and are wrong.**

> You cannot see that share from inside the pipeline, and you cannot estimate it from the failures:
> the missing work is in the successes, not in the errors. The measurement is cheap: draw a random sample of recent outputs, hand
> them to a strong model with a rubric, and report the rate every week. Without it, "0 errors" in the
> log is a statement about your checks, not about your output.

## Overview

| File | Job |
|---|---|
| `sample_outputs.py` | draw N random outputs from the last D days, redact paths/addresses/credentials, write a sample + manifest |
| `judge_prompt.md` | the rubric: invented fact, wrong requirement, internal contradiction, unsupported claim |
| `examples/weekly_report.example.md` | what the judge's output looks like, including a week where the checks said 0 |

## Why the rate matters more than the count

Recent work on verification measures the effect directly: the blind spot of a cheap verifier grows as
the verified model gets stronger, and an expensive verifier escalates far more cases than the true
error rate justifies (arXiv 2609.01345 reports escalation at 46% against a 39% error rate, and a
blind spot rising from roughly 0.12 to 0.55 across small-to-large students). Two practical
consequences, both in this folder:

- **Measure the successes.** Failure logs only contain what the checks caught.
- **Sample, do not exhaustive-check.** Judging every output with a strong model is exactly the cost
  you removed by automating. Twelve samples a week give a rate with a usable error bar; twelve
  thousand give a smaller one and no budget.

## How it works

`sample_outputs.py` walks a directory of job outputs, keeps files inside the window, draws a
deterministic sample for a given seed (so a rerun is comparable), redacts the local details that have
no bearing on quality, and writes:

```bash
python3 sample_outputs.py --dir ~/.hermes/cron/output --days 7 --count 12 --out blindspot_sample.md
```

The sample file and its JSON manifest are boring on purpose. A weekly job reads them with the rubric
and reports a table plus three lines: the rate, the most expensive error found, and one recommended
change to the checks or the prompt. That last line is the point of the exercise — the audit exists to
change something, not to score anything.

Redaction covers home paths, absolute system paths, IP addresses, e-mail addresses, credential-shaped
strings and coordinates. It is a filter for accidental disclosure, not a guarantee: review a sample by
hand the first time you point the tool at a new output directory.

## Limitations

- The judge is not ground truth. It catches what an attentive reader would catch; a shared blind spot
  between student and judge stays invisible.
- A rate from twelve samples is noisy: treat week-over-week movement under roughly ten points as
  noise, and read the trend, not a single report.
- Redaction is pattern-based. Prompts and outputs that quote unusual identifiers will not be covered.

## Directory structure

```
21-blind-spot-audit/
├── sample_outputs.py             # sample + redact + manifest
├── judge_prompt.md               # rubric for the judging model
├── examples/weekly_report.example.md
└── tests/test_sampler.py         # window, redaction, determinism
```

## License

Apache 2.0 — see the repository LICENSE.

## Disclaimer

The audit samples your own agent's output; the sample file is as sensitive as the outputs it came
from. Store it where the outputs live, not in a repository.
