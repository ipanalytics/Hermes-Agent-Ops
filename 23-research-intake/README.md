# 23 — research-intake

_Русская версия: [README.ru.md](README.ru.md)_

![License](https://img.shields.io/badge/license-Apache%202.0-blue)
![Status](https://img.shields.io/badge/status-active-success)
![Runtime](https://img.shields.io/badge/runtime-python%203.10%2B-informational)

**Read the literature as a corpus I count, not as a feed I scroll — and keep a journal of what I actually adopted.**

Hermes is the home AI agent I keep on my own server. It runs scheduled jobs — recurring tasks that fire at fixed times (every morning, every hour, every Monday at 09:00, the way one would write a recurring reminder) — and handles my routine work without supervision: a daily digest, a price watch, a health summary, a check on whether its own services are still alive. Most of those jobs have nothing to do with research. This folder is the one that does. It is the fixed way I harvest a category of papers from a public archive, count the same words over the same text week after week, and write down what I actually changed my mind about. The companion module 27 (`research-scout`) hunts for specific answers to specific questions; this one measures the drift of whole categories and feeds the result into a journal I read every Monday.

Most "trend" reports compare what an index chose to show this week with what it chose last week: a different sample every time, dressed as a direction. The chart moves because the search engine changed its mind, not because the field did. This folder takes the other route. I harvest a fixed set of papers through a harvesting protocol — a way to download everything in a category straight from the archive, instead of asking a search engine one question at a time — count words locally in equal windows, and keep every idea that survives a week in a journal with a first step, a metric and a kill date.

## Why it exists

A search API answers "what does the index think is relevant", one page at a time, subject to rate limits that have nothing to do with my usage pattern. I measured it directly: the arXiv query API returned rate-limit errors even for a trivial one-term query, from two different networks — so the limiting was not per-IP and not fixable by rotating egress (the network path my traffic leaves the building on). The harvesting protocol (OAI-PMH, the Open Archives Initiative Protocol for Metadata Harvesting — a small, polite XML-over-HTTP standard that lets a client walk an entire archive in order, page by page, with a bookmark that says "continue from here") has the opposite design. `ListRecords` with a set and a resumption token — a bookmark the server hands back so the next call can resume where the previous one stopped — walks a whole set, one request at a time. The arXiv OAI endpoint served thousands of records per week when the query API would not answer at all. Three seconds between requests is part of the deal; one request at a time, every time, is the price of a corpus that does not depend on anyone's ranking.

Counting then happens locally, over the harvested text, with the regexes (regular expressions — small text patterns that match words or word shapes) I control:

```bash
python3 oai_harvest.py --set cs:cs.AI --days 7 --out data/cs.AI.jsonl
python3 oai_harvest.py --count data/cs.AI.jsonl --terms examples/terms.json
```

That is what makes week-over-week comparison honest: same corpus shape, same patterns, no ranking changes underneath. Shares travel with the record count, because a week with twice the records inflates every absolute number. If I posted "X is up 30%" without telling the reader the corpus had doubled, I would have built a chart, not a measurement.

## The journal

| File | Job |
|---|---|
| `oai_harvest.py` | walk an OAI-PMH set with a resumption token, append JSONL, count terms offline |
| `direction_digest.py` | equal-window shares per term, marked only when a shift survives the comparison |
| `backlog.md` | the journal schema and the rules that keep it from becoming a museum |

`backlog.md` documents the schema I keep beside the corpus. Every idea that survives one week of reading has to be written down with these fields:

- `id` — a slug I can grep for. Lowercase, hyphens, stable across edits.
- `source` — where it came from (an arXiv id, a blog post, a hallway conversation). Without a source, "I read it somewhere" is the default and the idea cannot be re-checked.
- `found` — the date I noticed it. Without a date, "I have been thinking about this for years" becomes the default and nothing ever moves.
- `status` — one of four: `candidate` (I noted it, I haven't tried anything), `trying` (I have a first step running and a clock ticking), `adopted` (it changed something in the agent's routine), `rejected` (I tried it, the metric didn't move, here is why).
- `first_step` — the smallest action I can take this week. If I cannot name it, the entry is a note, not a candidate.
- `metric` — the number that decides whether it worked. "Better" is not a metric.
- `kill_by` — the date I stop waiting. After it, the entry is rejected with a reason.
- `reason` — required for `rejected`, worth filling in for the rest. "Tried it, the metric didn't move" is the most reused line in the file.

Two of the rules from `backlog.md` do the heavy lifting:

- **Equal windows, shares not absolutes** — otherwise a busy week reads as a trend.
- **Rejections keep their reason** — "tried it, the metric did not move" is the most reusable line in the file, and the only thing that stops the same idea from returning every quarter.

Three more that I learned the hard way and that live next to the schema in `backlog.md`:

- **No theory without a first step.** An entry that cannot name the smallest implementable action is a note.
- **One candidate at a time per area, with a rollback.** Two simultaneous changes to the same part of the system cannot be attributed later — if the metric moves, I have no way to know which one did it.
- **Prefer a script over a model.** If a step can be made deterministic, it stops competing for attention and budget with the steps that genuinely need judgement.

## Quick start

```bash
cp examples/terms.json .
python3 oai_harvest.py --fixture examples/oai_fixture.xml --out data/example.jsonl   # offline check
python3 oai_harvest.py --set cs:cs.AI --days 7 --out data/cs.AI.jsonl
python3 oai_harvest.py --count data/cs.AI.jsonl --terms examples/terms.json
python3 direction_digest.py --corpus data/cs.AI.jsonl --terms examples/terms.json --weeks 5 --out digest.md
```

The first run is offline: a saved response in `examples/oai_fixture.xml` gets parsed without touching the network, so I can see whether my regexes and date handling work before I burn a request on the live archive. The third run walks the arXiv `cs.AI` set for the last seven days and appends one JSON record per paper to `data/cs.AI.jsonl`. The fourth prints counts and shares. The fifth splits the corpus into equal time buckets and writes a digest that marks only the shifts larger than one percentage point — smaller moves get the equal sign, because most of them are noise inside a sample of that size.

## Outputs

- A JSONL file per set — one JSON object per line (JSON Lines: each line is a self-contained JSON record), one line per harvested paper, with id, title, abstract, creation date and subjects. Plain text, line-oriented, easy to grep, easy to re-process, easy to extend.
- Per-term counts and week-over-week shares, printed together with the record count — so a reader can see both the absolute count and the share, and notice when a share rose because the term grew and not because the corpus did.
- A digest marking only the shifts that survived an equal-window comparison, and a journal entry with a first step, a metric and a kill date for every idea I decide to try.

## Limitations

- Sets overlap and records are re-announced; dedup by identifier handles the common case, not every cross-listing. If a paper sits in two categories, it appears twice in my counts, and I have to live with that until I start joining on canonical ids. I trade completeness for transparency: any dedup that hides a record hides it from me too.
- Term counting measures vocabulary, not quality. A term can grow because more papers use the word in their abstracts, and I cannot tell from a count whether any of those papers are worth reading. The count tells me where to look; reading tells me what is there.
- OAI-PMH is polite by design: a full set walk takes minutes and several requests, with the three-second delay between calls. That is the price of a stable corpus, and it is cheap at one run a week. The end-to-end walk of `cs.AI` for the last seven days is well under a minute on my line; the bigger sets (`cs` as a whole) take a few minutes and are worth running overnight.

## Directory structure

```
23-research-intake/
├── oai_harvest.py                # ListRecords walk, JSONL, offline counting
├── direction_digest.py           # equal-window shares
├── backlog.md                    # journal schema + rules
├── examples/{terms.json,oai_fixture.xml}
└── tests/test_intake.py          # fixture parsing, counting, windows
```

## Related

- **27-research-scout** — the counterpart: it goes looking for specific answers, this one measures the direction of whole categories and feeds its findings into my journal.
- **20-task-evals-and-autopsy** — where my adopted ideas get checked once they become part of the agent's routine work.

## License

Apache 2.0 — see the repository LICENSE.

## Disclaimer

I respect the endpoint's terms and rate expectations: one request at a time, a descriptive user agent, no scraping beyond the protocol.