# 10 — cost-dashboard

_Russian version: [README.ru.md](README.ru.md)_

**One HTML file from the agent's usage database. Spend by day, spend by provider, top sessions by cost. Opens in any browser, runs no server.**

Hermes — the home AI agent that lives on my server — talks to several model providers around the
clock. Every call is logged: a timestamp, a session id, a provider, the number of input tokens,
output tokens and the cheap cached-input tokens (the repeated prefix the provider charges at a
fraction of the fresh-text price). All of that lands in a SQLite table called `session_model_usage`,
one row per session. `cost_dashboard.py` reads that table and renders a self-contained HTML page:
the total spend for the last N days, a per-day bar chart, a provider breakdown, and the top ten
sessions that ate the most money.

The role in the series is simple. Module 01 (`agent-wallet-guard`) is the **alarm**: it tells me a
budget is burning. This module is the **map** I open right after, to see which day, which provider
and which session did the burning. The alarm names the problem; the dashboard points at the room.

## Why it exists

A wallet alert without a breakdown is half an answer. Knowing "today is over the cap" doesn't tell
me whether a new model swap blew up the cost, whether a backup provider quietly became the primary,
or whether one runaway session ate forty percent of the week's budget while the rest of the agent
ran normally. Reading raw JSONL by eye misses the obvious: the bar that towers over its neighbours,
the provider whose slice grew month over month, the session id that shows up at the top of the
table three days in a row.

I don't want to ship a web app for this, and I don't want a JavaScript bundler chasing it. A single
`cost_dashboard.py --db state.db --out cost.html` invocation, cron it once a day, open the file when
the wallet guard alerts me or on the weekly review.

## What's in the box

- `cost_dashboard.py` — reads `session_model_usage` from a SQLite database, applies a price map
  (built-in defaults plus optional JSON override), and writes one HTML page. The page uses inline
  CSS and zero JavaScript; a single file opens in any browser.
- `examples/` — placeholder; supply a SQLite database with the right schema at deploy time.

## What I see on the page

The HTML has four blocks, stacked vertically:

1. **Header cards.** Estimated total for the window (default 14 days), number of sessions with any
   usage, the busiest single day.
2. **Spend by day.** A horizontal bar per day, scaled to the busiest one. Useful for noticing a
   spike that didn't trigger the wallet guard yet (it can be subtle below the daily cap).
3. **Top sessions by estimated cost.** Up to ten rows, sorted descending: session id (first 24
   chars), provider, call count, cache tokens, estimated dollars. This is the table that tells me
   "session `abc123…` is responsible for a third of the spend, on `secondary`, with 14M cache
   tokens — investigate."
4. **By provider.** One row per provider with its share of the estimated total. This is where a
   silent default change shows up: the slice that suddenly equals or exceeds the primary's.

The footer notes that these are *list-price* estimates (the price list in `--prices`, or the
built-in `DEFAULT_PRICES` for `primary` / `secondary` / `aux` if no override is given). Module 01
measures the **fact** from the provider's balance API; this dashboard measures the **attribution**,
so that I can act on it. The two numbers should agree to a few percent; if they don't, the price
list is the wrong one.

## How I use it

```bash
python3 cost_dashboard.py --db ~/.hermes/state.db --out ~/dashboards/cost.html
```

Three flags do the work:

- `--db` — path to the SQLite usage database. The script opens it read-only (`file:...?mode=ro`).
- `--days` — window length, default 14. Anything from 1 to "all of history" works; longer windows
  just make the per-day bars denser.
- `--out` — destination HTML, default `cost-dashboard.html`.
- `--prices` — optional JSON file overriding the built-in defaults; needed when my real prices
  drift from list or when I add a new provider.

I run it nightly from cron — pure SQL, no model calls, costs nothing — and open the file in a
browser when the wallet guard alerts me or as part of a weekly review. The HTML is small enough to
drop into a chat thread too.

## Limitations

- The schema is fixed. The script reads one table, `session_model_usage(session_id,
  billing_provider, first_seen, cache_read_tokens, input_tokens, output_tokens, reasoning_tokens,
  api_call_count)`. If a different deployment logs usage differently, the SQL has to be adjusted
  to match; the renderer stays the same.
- Estimates are only as honest as the price map. `--prices` overrides the built-in defaults, and
  I refresh it whenever a provider announces a change. Provider-side balance (Module 01) remains
  the ground truth for "how much did I really spend".
- Attribution is only as good as what gets logged. A local model run that isn't recorded into
  `session_model_usage` is invisible here. If I forget to add a row for a new inference path, the
  dashboard will quietly understate it.
- It is a report, not a control. Nothing in the HTML stops the spend. Module 01 alerts; Module 19
  (`cost-governance`) actually pauses the most expensive jobs. The dashboard is the layer between
  the two: it tells me *what to configure* the guard to watch.