# 24 — llm-to-script

_Русская версия: [README.ru.md](README.ru.md)_

![License](https://img.shields.io/badge/license-Apache%202.0-blue)
![Status](https://img.shields.io/badge/status-active-success)
![Runtime](https://img.shields.io/badge/runtime-python%203.10%2B-informational)

**The most expensive pattern in a scheduled agent is a model that fetches, parses, dedupes and ranks
on every run — and then writes two paragraphs at the end.**

> The inverted pattern is the same output for a fraction of the cost: a script collects and ranks, the
> model only formats. This folder is the shape of that conversion, the tool that finds the next
> candidate, and the numbers from two real conversions — including the one that removed 44% of a
> deployment's token spend.

## Overview

| File | Job |
|---|---|
| `collector.py` | reference shape: normalise → dedup by stable key → rank by explicit rules → artifact + one-line summary |
| `token_audit.py` | rank jobs by tokens, score them on input size and instruction density, shortlist the conversions |

## The inversion, in one table

| | Model does everything | Script collects, model formats |
|---|---|---|
| per run | fetch, parse, dedup, rank, write | read artifact, write |
| context | every fetched page, every candidate | the chosen items only |
| failure mode | silent, plausible output from a failed fetch | script exits non-zero; nothing is formatted |
| cost | thousands of input tokens per run | hundreds |

Two conversions from the deployment this series comes from:

- **A watchlist job** that polled a source and decided on every item: 53.7M tokens over the measured
  window, 44% of all spend, about 331k input tokens per run. Converted to a script that polls, filters
  and writes state: the recurring cost went to zero, because there is nothing left to reason about.
- **Three digest jobs** at roughly 557k / 941k / 841k input tokens per run, each re-reading and
  re-ranking the same sources. Converted to one collector plus a small formatter prompt: the
  collection is deterministic, the model writes one sentence per card.

## What belongs in a script

Four questions, in order. A "yes" to any of them means the step should not be in a prompt:

1. Would two runs with the same input be *expected* to produce the same output? (dedup, ranking, format)
2. Does it fail in a way a shell exit code can describe? (fetch, parse, validate)
3. Is the output consumed by code, not read by a human? (state files, queues)
4. Does it need no judgement about the world, only about the data in front of it? (filtering by a rule)

What stays with the model: choosing what matters, writing for a person, and deciding when to escalate.
The shortlist tool uses input size and instruction markers as a proxy, because the two are measurable
before the conversion and comparable after it.

## Quick start

```bash
python3 collector.py --input examples/feed.json --state seen.json --out cards.md --top 3
python3 token_audit.py --jobs jobs.json --audit usage_audit.jsonl --top 10
```

## Limitations

- A collector is code that can be wrong in a way a prompt cannot: it will not notice that the source
  changed shape unless you check for it. Pair the conversion with `18-harness-probes`.
- The shortlist is a heuristic. A small job with a dense prompt is not worth converting; a large job
  with a trivial prompt may be.
- Conversions are one-way in practice: once a job is a script, the ability to reason about edge cases
  moves into the code, where it must be written down.

## Directory structure

```
24-llm-to-script/
├── collector.py                  # normalise, dedup, rank, artifact
├── token_audit.py                # find the next conversion candidate
├── examples/{feed.json,rules.json}
└── tests/test_collector.py
```

## License

Apache 2.0 — see the repository LICENSE.

## Disclaimer

The numbers above come from one deployment and are reported as measurements, not benchmarks; your
sources, pricing and failure modes will differ.
