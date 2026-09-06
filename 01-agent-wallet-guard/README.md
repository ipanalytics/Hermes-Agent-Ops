# 01 — agent-wallet-guard

**Watchdog for LLM API spend: measure the *fact*, find the *culprit session*, alert only when something is wrong.**

## What you get here (real, runnable)

- `agent_wallet_guard.py` — the production watchdog (this exact logic ran every 30 min for weeks). Empty stdout when healthy; throttled alerts on: low balance (1/12h) and daily burn over threshold (1/4h), each with the top session by cache-read tokens as culprit candidate.
- `guard_config.example.env` — every knob, commented.
- `README.md` — you are here.

## The problem

Provider dashboards show totals, not *which session* burned the money. One giant session can silently eat a week of budget: a multi-hundred-K context replayed every turn, plus **compression attempts that hang 6–24 minutes and retry forever** — each retry a paid aux call on the main provider. Naive estimates from token price maps are wrong twice over: output prices drift ~2x, and cache-hit input (~50–100x cheaper than fresh) dominates real agent traffic.

## The design

1. **Anchor on the real balance** from the provider API at the first measurement of each UTC day.
2. A top-up re-anchors (a refill is not "burn").
3. Burn = anchor − current. When it crosses the threshold, query the usage DB for the day's fattest session and name it.
4. Network failure → stay silent. Scheduler integration: run every 30 min, empty stdout sends nothing.

## Hooking it into a cron (the way we run it)

`scheduler: every 30m, no LLM agent, stdout is delivered verbatim` — the script *is* the job.

## Why this gets stars

Money pain is universal; per-session attribution is rare; "silent when OK" is the alerting design people wish they had.
