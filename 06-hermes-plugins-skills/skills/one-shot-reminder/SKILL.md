---
name: one-shot-reminder
description: Use when setting a one-shot, fixed-text reminder (kitchen, errands, life) that must cost zero LLM tokens and self-disable after firing.
version: 1.0.0
---

# One-shot fixed-text reminder (no-agent cron)

The cheapest reliable reminder pattern: a scheduler job with NO LLM agent that
prints a fixed text; empty stdout sends nothing; after firing it disables
itself automatically. No model call, no prompt, no context.

## When to use
- "Remind me Wednesday evening to move X from the freezer"
- "Remind me Friday after 13:00 to buy Y"
- Anything fixed-text, one-time, action-anchored to the user's day.

## Recipe

1. Write a tiny script (bash is fine) under `scripts/`:

```bash
#!/bin/bash
# one-shot reminder
echo "🍽 Wednesday evening check:"
echo "- Move the portion from the freezer to the fridge — tomorrow is lunch day."
echo "- Salt: keep it soft 🙂"
```

2. Create the scheduler job:
   - schedule: absolute one-shot ISO timestamp in UTC (`2026-09-09T15:30:00`)
   - `no_agent: true`, `script: <your script>`
   - deliver: origin (the user's chat)
   - no prompt, no skills — the script IS the job

3. The job fires once, delivers stdout verbatim, and disables itself.

## Pitfalls
- **Timezones**: write the schedule in UTC; the user lives in Europe/Berlin
  (UTC+2 in summer). "17:30 Berlin" = `15:30 UTC`. Double-check before saving.
- **Anchor to the user's action**, not the bot's convenience: defrost the
  night before use, shopping reminder before the store closes, "took food to
  work" in the morning.
- **Don't spam**: if nothing needs saying on a given day, the script prints
  nothing and the run is silent (watchdog variant).
- **Empty stdout = nothing delivered.** A reminder script that always prints
  will deliver every tick — fine for one-shots, wrong for recurring.
