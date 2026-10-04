# 24 — llm-to-script

_Russian version: [README.ru.md](README.ru.md)_

![License](https://img.shields.io/badge/license-Apache%202.0-blue)
![Status](https://img.shields.io/badge/status-active-success)
![Runtime](https://img.shields.io/badge/runtime-python%203.10%2B-informational)

**I cut 44% off my agent's AI bill by handing one job over to an ordinary script.** Hermes is the
home AI agent I run on my own server: it does scheduled jobs — price watches, digests, health
checks, my own self-audits — most of them on a cron (a system scheduler that runs a command at a
fixed time, the same one Linux servers have used for decades). When the agent does a job, the
language model — the AI part, what people call an LLM — is the one paying attention and writing
text. But the model was also doing everything else: fetching the page, parsing the JSON, removing
duplicates, ranking results. That is paying AI rates for work a ten-line script does for free, on
my own CPU, with no prompt tokens at all.

> The inverted pattern gives the same output for a fraction of the cost: a script collects and
> ranks, the model only formats. Tokens — the units an AI model is billed for; one token is about
>  three-quarters of an English word, and providers charge separately for input and output — go
>  from thousands per run to hundreds. This folder is the shape of that conversion, the tool I
>  use to find the next candidate, and the numbers from two real conversions of mine.

## What "Hermes" is, for someone opening this folder

Hermes is the agent I built for myself. It lives on my own server, runs on a schedule, and is
where all my recurring AI work happens — watches, digests, monitoring of my own server and
infrastructure. Everything in this repository is one problem I solved once and want to keep
working. Each top-level directory is one module. This one is about paying for AI only when AI is
actually needed.

A "scheduled job" here means the same thing as a cron entry: a command that the system runs at a
fixed time, every hour or every day, without me being at the keyboard. The result of a job is
something I read later — usually a chat message, sometimes a file, sometimes a row in a database.

## Overview

| File | Job |
|---|---|
| `collector.py` | reference shape: normalise → dedup by stable key → rank by explicit rules → artifact + one-line summary |
| `token_audit.py` | rank jobs by tokens, score them on input size and instruction density, shortlist the conversions |

`collector.py` is the smallest version of the conversion that still does the job. It takes a
feed (a list of items in JSON), a state file (which keys I have already seen), and a rules file
(what counts as a good item), and writes a markdown artifact with the top picks. The model never
sees the full feed: it only sees the cards that survived ranking. That is the part I wanted to
spell out — the script does the deterministic, repetitive work; the model does the part where
judgement matters.

`token_audit.py` is the search tool. It reads a usage log — one JSON record per model call, with
job id, prompt tokens, completion tokens, timestamp — and a list of job prompts, and ranks the
jobs by total tokens. Each job gets two scores, both cheap to compute before the conversion:

- **median input size** — how many prompt tokens the job burns on every run;
- **instruction markers** — how many words in the prompt look like procedural instructions
  ("fetch", "parse", "if it fails", "otherwise", "verify"). These are the words that say "do
  things to data", and they are the ones that move into the script.

A job is on the shortlist when both signals fire — large input, dense procedure. That is where
the next conversion is hiding. The script does not promise every shortlist job is worth it; it
promises that jobs not on the shortlist almost never are.

## The inversion, in one table

| | Model does everything | Script collects, model formats |
|---|---|---|
| per run | fetch, parse, dedup, rank, write | read artifact, write |
| context | every fetched page, every candidate | the chosen items only |
| failure mode | silent, plausible output from a failed fetch | script exits non-zero; nothing is formatted |
| cost | thousands of input tokens per run | hundreds |

The right column is what I run now, and the numbers come from the same deployment — same traffic,
same feeds, just one role swapped. The middle row is the one I underestimated when I started:
the silent failure. If the model fetches a page that 404s, it can still write two confident
paragraphs about it, and I would only notice when a user complained. If the script has a bad
fetch, the script exits with a non-zero code (the standard Unix convention for "something went
wrong"), the cron sends me an error, and the artifact never gets written. The agent learns
about the failure from the absence of a result, not from a hallucinated one.

Two conversions from my own deployment:

- **A watchlist job** polled a source and decided on every item: 53.7M tokens over the measured
  window, 44% of all my spend, about 331k input tokens per run. I replaced it with a script that
  polls, filters and writes state — the recurring cost went to zero, because there is nothing
  left for a model to reason about. The script does the polling, the filtering, and the state
  update; the model never even starts.
- **Three digest jobs** at roughly 557k / 941k / 841k input tokens per run, each re-reading and
  re-ranking the same sources. I merged them into one collector plus a small formatter prompt: the
  collection is deterministic, the model writes one sentence per card. Three jobs became one
  collection step plus a single formatting call.

The watchlist is the clean win: when the whole job is mechanical, the model has nothing to do and
should not be in the loop. The digests are the careful case: I still want a human-sounding
sentence per card, but I do not want the model to also decide which sources to re-read. Splitting
the job at the right line is what makes both numbers true.

## What belongs in a script

Four questions, in order. A "yes" to any of them means the step should not be in a prompt:

1. Would two runs with the same input be *expected* to produce the same output? (dedup, ranking,
   format conversion)
2. Does it fail in a way a shell exit code can describe? (fetch, parse, validate)
3. Is the output consumed by code, not read by a human? (state files, queues, indexes)
4. Does it need no judgement about the world, only about the data in front of it? (filtering by
   a rule)

The order matters. Question 1 catches the work that is doing to be broken every time it runs in
a model — because the model is non-deterministic by design, two runs of the same prompt with the
same input will produce different texts, and that is fine for a paragraph but ruinous for a
dedup key. Question 2 catches the work whose failure should be loud — when a fetch returns 5xx,
I want the cron to email me, not the model to invent a confident summary. Question 3 catches the
work where readability is a cost, not a benefit: a state file the agent will read next run does
not need to be in prose. Question 4 catches the work that is essentially a filter — keeping
items where year == 2026 is a rule, not a judgement, and rules belong in code.

What I keep with the model: choosing what matters, writing for a person, deciding when to
escalate — the parts that need judgement, not memory. The model is at its best when its input
is already clean and small, and its output is read by a person. Anywhere the work is
mechanical, the model is the wrong tool, and not because the model is bad — because the model
is expensive and the work is not.

My shortlist tool uses input size and instruction markers as a proxy, because the two are
measurable before the conversion and comparable after it. I do not need to know whether the job
is worth converting in advance; I need to know whether it is large and procedural, which is what
the proxies say. The judgement about whether the conversion actually saves time comes after, in
the run that follows.

## Quick start

```bash
python3 collector.py --input examples/feed.json --state seen.json --out cards.md --top 3
python3 token_audit.py --jobs jobs.json --audit usage_audit.jsonl --top 10
```

`collector.py` reads `examples/feed.json` (four demo items), reads or creates `seen.json` (the
list of stable keys already shown), reads `examples/rules.json` (which year, quality, and tags I
prefer), and writes the top 3 cards to `cards.md`. The artifact is structured — title, link,
quality, year, tags — with one line per card reserved for the model's one-sentence description.
That reserved line is the seam: everything above it comes from the script, everything in it
comes from the model.

`token_audit.py` reads `jobs.json` (the list of cron jobs, with id and prompt text) and
`usage_audit.jsonl` (one JSON record per model call, written by the agent), and prints the top
10 jobs by total tokens with median input, marker count, and a flag for shortlist candidates.
The flag is the line that says "← кандидат на скрипт"; that line is what I look for when I want
the next conversion.

## Limitations

- A collector is code that can be wrong in a way a prompt cannot: it will not notice that the
  source changed shape unless I check for it myself. A model would produce a slightly off result
  and continue; a script will throw on a missing key. I pair every conversion with module 18,
  which watches the channel and detects shape changes; the script is responsible for parsing, the
  watcher is responsible for noticing when parsing breaks. The two together are sturdier than
  either alone.
- The shortlist is a heuristic. A small job with a dense prompt is not worth converting; a large
  job with a trivial prompt may be. The flag is a starting line for the conversation, not the
  end of it.
- Conversions are one-way in practice: once a job is a script, the ability to reason about edge
  cases moves into the code, where it has to be written down. If a job handles ambiguous input
  well because the model inferred what to do, that inference does not survive the conversion. I
  convert jobs where the input is well-defined and the output is structured, and leave the
  genuinely ambiguous ones to the model.

The unit tests in `tests/test_collector.py` cover the four things I worry about most: ranking
prefers what the rules say it should, dedup removes repeats, the state file grows by keys not
content (so it stays small), and the CLI writes an artifact and a one-line summary. I run them
whenever I touch either script; the tests take a few seconds and run without the network.

## Directory structure

```
24-llm-to-script/
├── collector.py                  # normalise, dedup, rank, artifact
├── token_audit.py                # find the next conversion candidate
├── examples/{feed.json,rules.json}
└── tests/test_collector.py
```

`collector.py` is the demo shape: 91 lines, no external dependencies, no network. It runs on
Python 3.10+ and exits 0 even when the feed has zero new items — silence is a valid result for a
collector. `token_audit.py` is 73 lines and reads whatever format the agent writes — it
gracefully skips malformed lines and never crashes on a single bad record. Both scripts use only
`argparse`, `json`, `pathlib`, `hashlib`, and `statistics`, which are all in the standard library.

## License

Apache 2.0 — see the repository LICENSE.

## Disclaimer

The numbers above come from my deployment and are measurements, not benchmarks; other sources,
pricing and failure modes will give other numbers.