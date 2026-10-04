# 29 — thinking-layer-cost

_Russian version: [README.ru.md](README.ru.md)_

![License](https://img.shields.io/github/license/ipanalytics/Hermes-Agent-Ops)
![Status](https://img.shields.io/badge/status-active-brightgreen)
![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue)

Every morning this one-page report tells me whether the spend on my "thinking layer" — the
expensive models I let Hermes reach for when a job needs real reasoning — is still inside the
ceiling I set for the day, and how many days the current API balance will last at the recent
pace. When the runway is short, I see it the same morning, not the day a request bounces.

## What Hermes is, and why this folder exists

Hermes is my home AI agent: it lives on my server, runs a stack of scheduled jobs by itself
(daily digests, price watches, health checks, self-monitoring of its own failures), and writes
small scripts for its own bookkeeping. Tokens are the units they bill against — roughly, every
word on the way in and every word on the way out — and "the thinking layer" is the subset of
jobs that I let use M3 and the advisor models that sit alongside it: the ones that actually
reason, instead of the cheap models I use for short mechanical lookups. Everything else in
the repository is one folder per solved problem; this folder is the one that watches the bill
on that subset specifically.

The reason this folder exists is that a budget ceiling I keep in my head does not hold. Token
spend drifts quietly: M3 becomes more verbose on a slightly more demanding prompt, one cron job
fires more often than I planned, an advisor model starts returning longer thoughts, and by the
time I open the dashboard the week has already cost more than I intended to allow. The day I
discovered this I had a balance that looked fine on Monday and did not look fine on Friday, and
I could not point at any single thing that had broken — every line had moved a little, in the
same direction, every day. A daily report with today's spend, the recent peak, the week's
average, the live balances, and an estimated runway turns the bill from a monthly surprise into
a number that moves a little each morning — the kind of number I actually react to.

## What the report prints, line by line

The script writes nine lines to standard output, in this order:

- the title with today's UTC date, prefixed with a money emoji so I can find it in chat;
- M3 spend today and total spend today, in dollars with three decimal places, plus the call
  count for M3 so I can tell cheap-and-chatty from expensive-per-call;
- the peak day in the past week, with its dollar value, and the average across the same
  window — both with two decimals — so I can see the spread between a typical day and a bad
  one;
- the per-million-token prices I am paying right now, for M3 and the two advisor models
  (GLM-flash and DS-0731), separated into input and output rates;
- the names of the jobs that count toward the thinking layer — the goal-judge step, the
  mixture-of-agents aggregator, and the "profile think" preset — so I can see why M3 is in
  the bill at all;
- the daily ceilings in dollars: a hard $1.50 cap on the ecosystem per day, and a $0.40
  cap on the thinking layer specifically, both echoed back in the report;
- the live balances from OpenRouter and DeepSeek (the two providers I buy model access
  from), with the estimated runway in days at the week's average pace;
- a status line: a green check mark when nothing is over its cap, a warning emoji with the
  words "above threshold" when either ceiling is crossed;
- a cache-hit line for the last 24 hours: the share of prompt tokens served from the provider's
  prompt cache, the split between fresh input, cached input and output tokens, the money spent
  in that window, and the top three models by spend with their own hit rate. This is the line
  that catches a policy that quietly stopped caching — the bill grows long before the report
  otherwise notices;
- one line per watched slot newcomer (optional): model name, day number out of `WATCH_DAYS`,
  calls, spend, cache hit and the reason it is being watched. The watch list lives in
  `~/.hermes/data/thinking_layer_watch.json`, not in the code.

The cron contract is the standard one for Hermes jobs: stdout is delivered as a message in my
chat, empty stdout is silence. There is no JSON dump, no file output, no CSV — the report is
meant to be read, not parsed. I keep the daily limit low so an overrun becomes a same-day
conversation instead of a month-end one.

## How the script gets the numbers

The script reads from three places and writes one block of text. In order:

1. `~/.hermes/state.db`, opened read-only — the SQLite database Hermes itself writes when
   each session records which model it called and how much that call cost. The query pulls
   the last eight days of `session_model_usage` rows, groups by date and model, and sums
   the call counts and the estimated dollar cost.
2. `~/.hermes/.env`, opened as text — the file Hermes uses for secrets; the script reads
   `OPENROUTER_API_KEY` and `DEEPSEEK_API_KEY` from it the same way other tools do, and falls
   back to the process environment if a key is set there instead.
3. Two live HTTP calls: `GET https://openrouter.ai/api/v1/credits`, which returns total
   credits minus total usage, and `GET https://api.deepseek.com/user/balance`, which returns
   the top-line balance. Both calls use a Bearer token, time out after twenty seconds, and
   fail silently to "n/a" if the key is missing or the provider is down.

From the SQLite pull, the script splits the rows into two sums: today's total spend across
every model, and today's spend on the thinking-layer subset (`{"minimax/minimax-m3",
"brain"}` — the two identifiers M3 and the brain preset can carry in the log). From the same
rows it builds a per-day map for the past seven full days, takes the maximum as the peak and
the mean as the average, and reports both. From the balances it computes runway as
`balance / average`, rounded down to a whole number of days, and only when the average is
non-zero — a fresh deployment with no history simply has no runway to print.

## Watching a newcomer model

When I put a new model into a slot, the interesting question is not "does it answer" but
"what does it cost at my real cache profile". A model can look cheap on the price list and
still cost more than the one it replaced, because the cache-hit rate is what dominates a
long-running agent: most of the prompt on every call is the same prefix, and the per-million
cache-read rate differs between models by an order of magnitude. So for the first
`WATCH_DAYS` days (5 by default) the report prints one extra line for that model: day number,
call count, spend, and its cache-hit share, next to a short note on why it is being watched.
After the window the line disappears by itself.

The list is data, not code: `~/.hermes/data/thinking_layer_watch.json`, shaped as

```json
{"<model-id>": ["<YYYY-MM-DD start>", "<why this model is being watched>"]}
```

A missing or malformed file simply means nothing is watched. I keep the file out of the
repository on purpose: the note usually names the slot the model is auditioning for and
what it would have to beat.

## The thinking-layer definition

The thinking layer is the small set of model identifiers I let carry the hard reasoning in my
stack: `minimax/minimax-m3` for the M3 calls themselves, and `brain` for the brain preset
that some jobs route through. Everything else in the daily bill — short classifiers, JSON
shaping, quick lookups — runs on the cheaper advisor models (GLM-flash at $0.15 per million
input tokens and $0.50 per million output, DS-0731 at $0.065 and $0.18) and is reported in
the "total per day" line, not in the thinking-layer line. The per-million rates I am paying
right now for those three models are echoed back in the report itself, so a future me (or
anyone reading the message in chat) can see what each call is costing without having to
remember the price list.

The ceilings I hold myself to are $1.50 a day across the whole ecosystem and $0.40 a day on
the thinking layer specifically. These are values at the top of the script and they are
deliberately small: the goal is to surface a problem on the morning it starts, not three days
later when the provider has already cut me off. When either ceiling is crossed, the status
line flips from a green check to "above threshold" and that is the morning I open the larger
dashboard and decide which job to move or which model to swap.

## Quick start

```bash
python3 thinking_layer_cost.py
```

Before the run, set the two API keys either in the environment or in `~/.hermes/.env`:

- `OPENROUTER_API_KEY` — to read the OpenRouter credit balance
- `DEEPSEEK_API_KEY` — to read the DeepSeek balance

If either key is missing, the corresponding balance line prints `n/a` and the rest of the
report still runs; the script does not abort on a missing provider. The state database path
defaults to `~/.hermes/state.db`; I override it with `HERMES_HOME` when I want to point at a
sandbox copy of the deployment.

## Outputs

- Today's spend on M3 and the brain preset, with the call count.
- Today's total spend across every model.
- The peak daily spend in the past seven days, and the average across the same window.
- The per-million-token prices I am paying for M3, GLM-flash, and DS-0731.
- The current balances on OpenRouter and DeepSeek.
- An estimated runway in days, computed at the week's average pace.
- A status indicator: green check, or "above threshold" when either daily cap is crossed.
- A 24-hour cache-hit line: hit share, input/cache/output split, spend, and the top spenders.
- Optional per-model lines for watched newcomers, for the first `WATCH_DAYS` days.

## Limitations

- The script needs read access to `~/.hermes/state.db`, the database Hermes itself writes.
  On a fresh deployment with no recorded calls, the per-day lines are empty and the
  report still runs; it simply has no numbers to show.
- The two live balance calls need valid `OPENROUTER_API_KEY` and `DEEPSEEK_API_KEY`. A
  missing key produces `n/a` for that provider and no abort; the rest of the report is
  unaffected.
- Date arithmetic is done in UTC; the "today" line is whatever date it is in UTC at the
  moment the cron job fires. On days when my schedule puts the run after a UTC midnight
  rollover, "today" is the new UTC date, not my local one.
- The report is a single snapshot, not a trend. The peak and average are computed over the
  past seven full days, which is short enough to follow the current assignment but does not
  catch slow drifts that take longer than a week to become visible.

## Structure

```
29-thinking-layer-cost/
├── thinking_layer_cost.py            # the daily-report script
├── tests/test_thinking_layer_cost.py # tests for constants, the .env reader and the watch list
└── examples/
    ├── config.json                   # keys the script expects to find
    └── thinking_layer_watch.example.json  # optional watch list for a newcomer model
```

`thinking_layer_cost.py` is a single file, around 200 lines, and depends only on the standard
library (`json`, `os`, `sqlite3`, `urllib.request`, `datetime`). The two API calls use a
20-second timeout and swallow exceptions into `None`, so a flaky provider never aborts the
report. The tests in `tests/test_thinking_layer_cost.py` cover the constants the script
exposes (`THINKING`, `DAY_CAP_USD`, `THINK_CAP_USD`) and the `env()` reader, including the
fallback when the `.env` file is missing. `examples/config.json` is a placeholder for the
two API keys plus `HERMES_HOME`, the way the rest of the Hermes ops scripts document the
secrets they expect.

## Related

- **30-schedule-audit** — the lever I reach for when this report points at it: when the
  runway is too short, the heavy cron jobs move to night hours and the daily ceiling gets
  another morning to breathe.
- **31-compaction-effect-check** — another before-and-after cost check, the one I use on
  days when the change is in the compaction policy (how Hermes summarises its own older
  messages to fit them in the model's context window) rather than in the schedule.
- **19-cost-governance** — the broader rules I keep for the whole stack; this folder is the
  daily heartbeat that tells me whether the rules are still being followed.

## License

MIT — see the LICENSE file in the repository root.