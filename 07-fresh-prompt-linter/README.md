# 07 — fresh-prompt-linter

_Russian version: [README.ru.md](README.ru.md)_

![License](https://img.shields.io/github/license/ipanalytics/Hermes-Agent-Ops.svg)
![Status](https://img.shields.io/badge/status-production-green.svg)
![Python](https://img.shields.io/badge/python-3.10+-blue.svg)

My code-review bot for prompt hygiene. A "prompt" is the instruction text an agent job runs with; a
scheduled job gets a brand-new session with no memory of any past conversation, and this bot checks
the prompt before it ships — so words that assume history never reach the schedule.

## What Hermes is (for a new reader)

Hermes is the AI agent I run on my own server. It does the recurring work I do not want to remember:
daily digests, price watch, stock checks, health routines, looking at its own logs for problems. Most
of that work is fired by a scheduler ("cron" — a system job that runs unattended at fixed times).
When a cron slot opens, Hermes starts a brand-new session: no chat history, no memory of prior
conversations, nothing. The only thing it sees is the prompt text the scheduler feeds it.

That single fact — *the job gets a fresh session every time* — is what this folder is about.

## Why this exists

A scheduled job is not a chat. In a chat I can say "as I said earlier" or "the file mentioned
earlier" and the model knows what I mean. In a cron slot there is no "earlier". I learned this the
hard way: a prompt I considered obvious contained "as noted above" and a relative date, the job
opened at 03:00 with an empty context, hallucinated a file path, stalled, and the digest for that
day never landed.
"<thing>" or `{{x}}` mean a template was forgotten. "Ask me" / "I'll wait" / "please confirm"
assume a human on the other end who never shows.
A prompt that says nothing about how to deliver the output — just "do the thing" — usually produces
silently dropped work. I wrote `fresh_prompt_linter.py` to catch all of these before they go on the
schedule.

## What the linter actually checks

The checks are heuristics — known-bad shapes, not a guarantee. A prompt can pass the linter and still
fail in production, and it can fail the linter and still work. Treat it as the cheap bot that reads
every prompt before deploy and refuses to sign off on the obvious ones.

1. **Anaphora / history references.** Phrases like *"as I said earlier"*, *"see above"*, *"the file
   discussed earlier"*, *"as you know"* — these have no referent in a fresh session. FAIL.
2. **Relative time without a date anchor.** Words like *today*, *yesterday*, *this week*, *now*,
   *recently* are only safe when the prompt also contains an explicit date (`2026-10-04`, `04.10.2026`,
   `October 4`). Without an anchor, "today" is whatever day the cron happens to fire. WARN.
4. **Interactive verbs.** *"ask me"*, *"I'll check back"*, *"please confirm"*, *"shall I"*, *"hold on"* —
   a scheduled job has nobody to answer, so the run stalls forever. WARN.
5. **Unresolved placeholders.** `{{x}}`, `${x}`, `<thing>` — someone forgot to template the prompt
   before shipping. FAIL.
6. **No delivery instructions.** If the prompt never says how to report (no `output`, `format`,
   `reply`, `send`, `json`), the job usually completes and silently disappears. WARN.
7. **Length floor.** A prompt shorter than 200 characters almost never carries enough rules for a
   fresh session. WARN.

`--allow` lets me whitelist substrings inside the prompt (e.g. a quoted example sentence) so the
linter does not double-count patterns I deliberately wrote as documentation.

## Quick start

```bash
python3 fresh_prompt_linter.py --prompt-file my_job_prompt.md
echo $?   # 0 = OK (warnings only), 1 = FAIL — block the deploy
```

I run it in CI on every change under `~/.hermes/cron/`. The exit code is the contract: CI fails,
the prompt does not ship, I fix it.

## Limitations

- **Heuristic, not semantic.** It reads patterns, not meaning. "Remember the previous incident"
  triggers FAIL even if "previous incident" is referenced by name further down. Read the FAIL list
  before refactoring — sometimes the right answer is `--allow`.
- **English- and Russian-shaped regex.** The two languages I write prompts in. Add a new language
  by extending the rule lists in `fresh_prompt_linter.py`; the rest of the tool does not care.
- **No model call.** It is deliberately regex-only. Calling a model to review a prompt would cost
  tokens and time on every prompt change, and the model would still need a fresh session to be
  trustworthy. The whole point of this folder is the cheap gate.

## What's in the folder

- `fresh_prompt_linter.py` — the linter itself, single file, no dependencies.

## License

MIT