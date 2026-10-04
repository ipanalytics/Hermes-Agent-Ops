# 27 — research-scout

_Russian version: [README.ru.md](README.ru.md)_

![License](https://img.shields.io/github/license/ipanalytics/Hermes-Agent-Ops)
![Status](https://img.shields.io/badge/status-production-green)
![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue)

Every morning at six, a cron tick on my server writes two files: a small markdown list of the
few new arXiv papers worth opening, and a one-line fingerprint printed to stdout for the gate
that watches the job. I do not read the arXiv firehose; the script does, and I read two pages.

## What arXiv is, and what I actually need from it

arXiv is the largest open library of research papers in computer science. Every day it gets
hundreds of new submissions across the categories I actually follow: artificial intelligence,
machine learning, natural language processing, agents. Reading that much is impossible;
filtering it by hand was worse. The spreadsheet attempt lasted about a year before the unread
pile outgrew the fresh one and the file stopped getting opened. Papers missed in the first
week tend to reappear two months later as someone else's benchmark baseline, and by then the
right move is to react to the field instead of working in it.

A cron job — a scheduled task that runs without me remembering anything — has no such curve.
It reads everything every day, keeps a journal of papers it has already judged so nothing is
seen twice, and leaves a small ranked file instead of a firehose. A relevant paper found early
is worth an hour of reading; the same paper found two months later is worth nothing, because
someone else already built on it.

## Why it exists

I wrote this script the morning after the third time a paper I would have used landed in a
benchmark I read six weeks later. The failure was not that the paper had disappeared — it
hadn't. The failure was that there was no signal on my desk that it had landed. A scheduled
reader that runs without me does not fix the overdue reminder problem on its own; it also
has to write its results somewhere I will actually open, and it has to be transparent when
it has nothing new to say, so the gate that watches it does not mistake silence for a
breakage.

This folder is the morning-readout part of my research loop. The rest of the loop — picking
which paper to open, running the experiment, writing the note — is mine.

## What a cron job and a gate are

A cron job is a task the system runs on a schedule: every morning, every hour, every Sunday,
without anyone at the keyboard. Hermes keeps its list of these tasks in
`~/.hermes/cron/jobs.json`. Each task has an id, a name, the model that runs it, an enabled
flag, and a `last_status` field written by the agent after the run.

A gate is a check that compares a scheduled run's output against an expected line. If the
output matches, the run is considered successful and the gate stays silent. If the output
changes — or worse, goes missing — the gate raises a flag, because a cron that suddenly
changes its output usually means the process under it changed, not that the world did. The
fingerprint this script prints to stdout is the line the gate watches. There is no timestamp
in the line on purpose: a timestamp would change the fingerprint every run and the gate
would never see a silent morning.

## How it works

1. The script calls `~/.hermes/scripts/arxiv_fetch.py oai --set cs --from YYYY-MM-DD --until
   YYYY-MM-DD --max-pages 12`. OAI-PMH is the protocol arXiv exposes for bulk metadata
   delivery. Unlike the search API, it does not need a query and returns the records in the
   same shape every time, so the whole six-day window can be ingested without burning a rate
   limit. arXiv's OAI-PMH only knows top-level sets like `cs` — subsets such as `cs:cs.AI`
   are rejected by the server, which is why the script asks for `cs` and does the
   per-category filtering itself.
2. Each paper is scored by my regex theme patterns — small hand-written search patterns
   describing what I am actually working on right now. The strong themes are `harness`
   (agent scaffolding, tool use, function calling, orchestration), `evals` (benchmarks,
   verifiers, rubrics, reward models, regression suites), `memory` (long-term memory,
   context engineering, context management), `routing` (model selection, escalation,
   cost-aware and tiered routing), `determinism` (deterministic workflows, script and
   program synthesis, compiled agents), `sandbox` (isolated execution, permission models,
   capability restriction), and `agentcore` (autonomous agents, agentic workflows, LLM
   agents). The weaker themes — `cost`, `multiagent`, `safety` — are kept as backup
   signals. A match in the title is worth three times a match in the abstract, on the
   assumption that the author already wrote the most relevant word where the reader looks
   for it. A paper with a total score below three is dropped: it keeps the morning file
   from getting padded with papers I would not actually open.
3. Each paper gets a second number from Hugging Face's daily papers endpoint — a public
   counter the community uses to vote "this was interesting" on each paper. The script
   pulls the latest 40 plus a per-date lookup for each of the six days in the window,
   because the latest list is short. The HF vote is the only free acceptance signal I have
   without a key, and it is independent from my own scoring, so when both agree the paper
   is worth opening first. Final order is by my score, with HF votes as tiebreaker, then
   truncated to `MAX_ITEMS = 7` papers.
4. Each picked paper is deduplicated against `~/.hermes/data/research_scout_seen.json`, the
   journal of every paper the script has ever judged. The journal is capped at the last
   5000 entries; older entries fall off, which is fine — a paper older than that is no
   longer "new". If the cache file `~/.hermes/data/research_scout_cache.json` is fresher
   than `CACHE_MINUTES = 30`, the script reuses the cached fingerprint instead of
   collecting again: a second tick in the same minute, and any other scheduled tick that
   lands inside the half-hour window, gets the same output and the gate stays silent.

If nothing new survives the filters, the script writes nothing to the markdown file and
prints the same constant string to stdout: `no new relevant arXiv papers`. That is the
whole point: the gate sees an unchanged fingerprint, and an empty morning is
indistinguishable from a normal morning until I open the file myself and notice.

## Quick start

```bash
python3 research_scout.py
```

Window length, cache timeout, maximum picks, and the theme regex patterns themselves are
all constants at the top of `research_scout.py`. I edit them in place and keep the script
in a daily cron entry that calls it once per morning.

## Usage

The script is meant to run without arguments and without anyone watching. Every setting it
reads is a constant in the file:

- `WINDOW_DAYS = 6` — the lookback window. Six is the smallest window that survives a
  weekend without leaving a gap, and small enough that the OAI-PMH fetch finishes well
  inside the cron tick budget.
- `CACHE_MINUTES = 30` — the freshness window for the cache file. A second invocation
  inside this window returns the cached fingerprint without re-fetching.
- `MAX_ITEMS = 7` — the morning reading list is never longer than seven papers. The cost
  of reading more is mine, not the script's, and seven is what I can finish before lunch.
- `THEMES` — the dictionary of theme name to regex pattern, with `STRONG = {harness,
  evals, memory, routing, determinism, sandbox, agentcore}` separating the themes I
  actively follow from the backup signals. I add a theme by editing the dictionary; I drop
  one by removing the entry. The test in `tests/test_research_scout.py` makes sure the
  constants stay defined and positive.

The fingerprint the script prints to stdout is a single line of `id|score|votes|tag1,tag2,…`
rows joined by newlines, one row per picked paper. When the script is in cache-reuse mode,
it prints the cached fingerprint verbatim, so the gate sees exactly the same line it saw
last time.

## Outputs

Four things happen on every run:

- `~/.hermes/data/research_scout.md` — the ranked morning reading list. Each paper gets a
  numbered section with its title, the arXiv id, the publication date, my theme score, the
  comma-separated themes that fired, the HF vote count, a 200-character abstract, the
  arXiv URL, and an empty `for me: (write 1 line — what this gives my agent)` line I fill
  in by hand after reading. At the bottom of the file is a `MODEL TASK:` block that asks
  the next model to summarise what is new and why it matters, where to apply it — module or
  cron — what to publish in the public series, and one idea for future work. If reception
  is disputed, the model is told to say so directly. Reviews are capped at one per paper.
- `~/.hermes/data/research_scout_seen.json` — the journal of papers the script has
  already judged, kept as a sorted list of strings and capped at the last 5000 ids.
- `~/.hermes/data/research_scout_cache.json` — the cache file the script writes for the
  next call inside the 30-minute window.
- stdout — the stable fingerprint the gate watches.

The fingerprint line deliberately contains no timestamp, no run counter, no machine name:
just the ids, scores, vote counts, and tags of the papers actually picked. A timestamp
would change the fingerprint every run and the gate would never see a silent morning.

## Limitations

- The script depends on arXiv OAI-PMH being reachable and on the Hugging Face daily papers
  endpoint returning upvote counts. If either is down, the corresponding signal is missing
  but the script still produces a fingerprint from the other.
- Theme filtering is regex-based and hand-written. A paper that hides the relevant word
  behind a synonym, or that talks about my themes without naming them, will not be picked
  up until I edit the pattern. The weak-themes bucket catches some of those, but not all.
- The window covers only arXiv's `cs` set today. Other sets (`stat`, `eess`) are not
  fetched, because the cron tick budget would not survive the extra pages.
- The score threshold (`total < 3 → drop`) is a blunt instrument: a paper that scores
  exactly two will not appear in the morning file even if it is the most important paper
  of the week. I lower the threshold when the morning file is empty for too many days in a
  row.

## Structure

```
research_scout.py                # Main script
README.md                        # This file
README.ru.md                     # Russian translation
tests/test_research_scout.py     # Tests for theme scoring and constants
examples/config.json             # Sample theme and window configuration
```

The script is a single 198-line file with no dependencies outside the Python standard
library (`json`, `re`, `sys`, `time`, `urllib.request`, `datetime`, `pathlib`). It runs
on Python 3.10+. The test file checks the scoring logic: that a title match is worth three
points, that an abstract match is worth one, that case does not matter, and that the
constants stay defined and positive.

## Related

- **28-digest-delivery-health** — the delivery-side counterpart: another of my scheduled
  jobs, watched by the same kind of gate. Together with this script it forms the
  morning-readout pair — research-scout picks the papers, digest-delivery-health checks
  that the digests citing them actually arrive.
- **30-schedule-audit** — where I fit this cron job into the nightly schedule when it
  starts to cost real money. The script is small enough today that the cost is negligible,
  but if the OAI-PMH fetch ever needs to expand, that module is where I look first.

## License

MIT