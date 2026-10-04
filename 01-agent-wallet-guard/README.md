# 01 — agent-wallet-guard

_Russian version: [README.ru.md](README.ru.md)_

**Watchdog for LLM API spend: measure the *fact*, find the *culprit session*, alert only when something is wrong.**

This is module 01 in a series of scripts that came out of running a personal AI agent at home. That agent — called **Hermes** — lives on a server of mine, works around the clock, takes care of its own routine (digests, price watching, health tracking, monitoring its own failures) and writes the scripts it needs. Each folder in this repository is one such script: a single problem I had to solve and a tool that solved it.

For a reader new to this corner of the stack: an **LLM** (*Large Language Model*) is the AI I pay to respond to text, billed per **token** (roughly a word or fragment of a word) for each chat — a **session** is one continuous conversation. A **scheduled job** (or **cron job**) is a task that fires on a timer — here, every 30 minutes — without me being there. The watchdog in this folder is one such scheduled job: it measures the real balance on the provider, names the session doing the most damage, and only speaks up when something is actually wrong.

## Why it exists

The provider's dashboard shows totals — how much I have spent today, this week, this month. It does *not* show *which session* burned the money. I learned that the hard way: a single giant session silently ate a week of my budget. The **context** — the running history the model re-reads every turn — had grown to several hundred thousand tokens, and the agent kept replaying it on every step. On top of that, **compression attempts**, where the assistant tries to squeeze a long conversation into a smaller summary, kept hanging for 6 to 24 minutes and then retrying; every retry is a paid auxiliary call on the main provider, billed at full price. A stuck compression is not a paused system — it is a quietly running meter.

My own estimates from token price maps were wrong twice over. The price for **output tokens** drifts by about 2× over time, so the number in a config file was rarely the number on the actual invoice. And the input side is not what it looks like either: when the same prefix of the prompt is sent again, most providers treat it as a **cache hit** and bill it at roughly **1/50 to 1/100 of the fresh-input rate**. For real agent traffic — where the long history of a session gets re-sent every turn — that cache-hit input dominates the bill.

The only honest number is the balance the provider itself reports through its account API. The only useful alert is one that names a session, so I can go look at it and reset it if it has gone bad. Everything else in this folder follows from those two facts.

## How it works

1. **Anchor on the real balance** the provider reports, at the first measurement of each UTC day. Everything else is a delta off that anchor.
2. If a top-up happened, the script detects that the balance went *up* and resets the anchor. A refill is not burn.
3. **Burn = anchor − current balance.** When the burn crosses the daily threshold, the script queries the usage database for the session that has consumed the most cache-read tokens today, and names it as the culprit candidate.
4. **A network failure is not an alert.** If the provider's API is down or my request times out, the script says nothing and waits for the next tick.

Alerting is throttled so I do not get woken up at 3 AM for the same thing twice in a row: a low-balance alert fires at most once every 12 hours, a daily-burn alert at most once every 4 hours. Each alert carries the top session by cache-read tokens as the candidate to look at — because in this setup, the session that is replaying hundreds of thousands of tokens every turn is the one that actually moves the needle. The healthy case is the loudest part of the design: the script prints nothing, which means my delivery channel stays silent. Empty stdout is success.

## Files and how it runs

The script is `agent_wallet_guard.py`. The companion file `guard_config.example.env` lists every knob with comments. My scheduler integration is the entire deployment:

```
scheduler: every 30m, no LLM agent, stdout is delivered verbatim
```

— the script *is* the job. Every 30 minutes it runs, and an empty stdout sends nothing.

Minimum that needs to be set:

```bash
WALLET_BALANCE_URL=https://api.deepseek.com/user/balance
WALLET_API_KEY=sk-...                  # or use WALLET_API_KEY_ENV=DEEPSEEK_API_KEY
WALLET_LOW_BALANCE=2.0                 # USD floor (default 2.0)
WALLET_DAILY_BURN=1.5                  # USD burn/day that triggers (default 1.5)
```

To get the **culprit session** line, point the script at a sqlite database with a `session_model_usage` table (columns `session_id, billing_provider, first_seen, cache_read_tokens, input_tokens, output_tokens, reasoning_tokens, api_call_count`):

```bash
WALLET_USAGE_DB=/var/lib/agent/state.db
WALLET_PROVIDER=deepseek               # billing_provider value to filter on
```

The state — the daily anchor and the timestamps of the last low-balance and daily-burn alerts — lives in a small JSON file, default `~/.cache/agent_wallet_guard.json`. The script creates the directory on first write, so there is nothing to set up by hand. The internal threshold for flagging a session as a "monster candidate" is 40 million cache-read tokens in a single UTC day. A network failure is silent by design — if the provider is down for six hours, the script will not tell me, because I would rather not get an alert every 30 minutes because the provider is having a bad day. The script reads a balance from the provider's account API; if the provider does not expose one, or my key does not have read permission, the script has nothing to anchor on.

## Related

- **10-cost-dashboard** — the dashboard that shows *where* the burn went, after this watchdog has told me there is a burn to look at.
- **03-agent-ops-playbook** — the incident reports that document, among other things, the budget-eating session this script was written for.
- **29-thinking-layer-cost** — a more focused watch on the reasoning-side of the spend.