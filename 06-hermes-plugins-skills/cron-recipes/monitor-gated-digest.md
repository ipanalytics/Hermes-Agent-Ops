# Cron recipe: monitor-gated LLM digest (wake the model only on change)

Goal: a recurring LLM digest (prices, news, watchlist) that costs tokens ONLY
when something actually changed.

## Ingredients

- `monitor`: a cheap change-detector — a script or an http(s) URL fetched
  every tick. NO LLM. Output compared with the previous tick.
  - identical output → the agent run is **skipped entirely** (zero tokens)
  - changed output → the agent wakes with the diff injected into its prompt
  - first tick always runs (baseline)
- The monitor output must be **deterministic** (no timestamps!) or every tick
  looks changed and the gate is useless.
- `continuity: true` on the agent job: it sees its own previous output, so it
  can dedupe against what it already reported.

## Shape

```
tick ─▶ monitor (script/URL, cheap)
         ├─ same as last tick ─▶ skip agent (silence, $0)
         └─ changed ─▶ LLM agent (prompt + diff) ─▶ digest to topic
```

## Example: price watch

- monitor: curl the product page / API, extract the price number only
- agent prompt: "price changed from X to Y — is it below the threshold? alert
  or stay silent" + delivery rules (silent when above threshold)

## Example: release watchlist

- monitor: RSS parser output (titles + links, sorted, stable format)
- agent: on diff — filter against the user's taste, format cards, deliver

## Pitfalls

- Prompt must be **self-contained**: the cron agent sees no chat history.
  Preferences, thresholds, anti-keywords — all in the prompt.
- Digest dedupe via continuity: compare with previous output, send only the
  delta; "already shown" collapses to one line.
- Alert on top: a threshold breach is the FIRST line, big, with a plan B.
- Silence is a feature: unchanged price/status → one short line or nothing.
