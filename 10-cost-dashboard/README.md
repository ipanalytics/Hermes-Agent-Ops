# 10 — cost-dashboard

_Русская версия: [README.ru.md](README.ru.md)_

**See where the money went: one-file HTML panel from the usage DB — spend by day, by provider, and the top sessions that ate your budget.**

> `01-agent-wallet-guard` tells you WHEN money burns. This tells you WHERE.
> The guard measures the fact (provider balance); the dashboard attributes it
> (per session/day/provider). Guards + attribution = you stop guessing.

## What you get here

- `cost_dashboard.py` — reads the same sqlite usage table as the guard and renders a self-contained HTML page: no server, no JS frameworks, one file you can open anywhere or serve statically.

## What it shows

- **Total estimated spend** over the window, sessions with usage, busiest day.
- **Spend by day** — bars; a 7x cliff is the signature of a runaway session.
- **Top sessions by estimated cost** — session id, provider, call count, cache tokens. The runaway is at the top (sorting by cache-read tokens is the honest order: cache hits dominate agent traffic and are the #1 tell of a context swamp).
- **By provider** — where the aux vs conversation split really lands.

## Estimates vs measured balances

Token prices are estimates from list prices (override via `--prices`). The page footer says it:
the dashboard is for *attribution*, the wallet-guard is for *fact*. Never bill from the
dashboard, never debug from the guard alone.

## Pairing

- `01` guard alerts with the culprit session id → open the dashboard → reset that session.
- The usage schema is shared with `01`, so the two tools drop into the same DB.
