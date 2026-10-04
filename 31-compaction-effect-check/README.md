# 31 — Compaction Effect Check

_Russian version: [README.ru.md](README.ru.md)_

![License](https://img.shields.io/github/license/ipanalytics/Hermes-Agent-Ops)
![Status](https://img.shields.io/badge/status-active-brightgreen)
![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue)

I changed how the agent compacts its context — a new threshold, a different compaction model, a
smaller tail — and I wanted to know whether it had helped. "Helps" is the wrong word, because
"helps" can mean cheaper, or faster, or just less awkward to read, and these three do not move
together. The honest answer needs two windows of real traffic, one before the change and one
after. This folder is the measurement I use, so "it feels lighter since the change" is never my
evidence.

## What compaction means, and why it is the dangerous knob

Context compaction is the step where the agent summarises its older messages so the conversation
fits inside the model's context window — the maximum amount of text the model can read at once.
Hermes does this automatically, the same way any long-running agent has to. Compaction is also
where the model has to spend tokens: a separate model is asked to read the recent turns and
write a shorter version that preserves what is still needed. That second model is what bills me.

The reason compaction is the easiest place to make a change that looks like an improvement and
costs money:

- A compaction model that is three times cheaper per token but fires twice as often is not
  cheaper. I learned this by watching the curve.
- A lower threshold frees context sooner and quietly bills me on every following turn, because
  the cached prefix no longer matches. Most modern endpoints discount repeated tokens, but only
  when the prompt starts the same way; a fresh summary breaks that prefix, and the next turn
  pays full price for what would have been discounted.
- A compaction triggered only at the wall leaves the biggest sessions — the ones with the most
  to gain — untouched, because they never get a clean moment to compact in. The long-running
  debugging session is exactly the one I most want compacted, and it is the one that will not
  get there if compaction only fires near the limit.

None of that is visible in the moment. It shows up in the cost curve a week later, which is why
the change has to be measured against its own before-and-after windows instead of judged by how
the session felt afterwards. The session feels lighter in both cases — that is the trap.

## Why it exists

This folder exists because I caught myself approving compaction changes by feel. The deployment
ran for two months on the old settings, I changed the model, the daily cost went down by about a
third, and I felt clever. A week later the cost was higher than before the change, and I had no
record of which knob I had touched. I wrote this script the same evening. Anything that touches
money needs a number to defend itself, and "I think this is faster" is not a number.

The other reason it exists: I do not want to compare compaction changes against each other by
memory. The threshold and the model and the tail interact, and the only honest test is one
change at a time, in its own window, with the before-state and after-state both on disk. The
script is the boring part of that discipline: it does not decide what to change, it just
records what was true before and what became true after.

## How it works

1. Before the change, the script collects a baseline over a configurable number of days: daily
   cost, how much of it is compaction, and the cache-to-input ratio — the ratio of discounted
   cached tokens to full-price input tokens, which tells me how often the prefix survived.
2. I record the exact timestamp of the change. There is no way to reconstruct it later, which
   is why it is a required input rather than a guess.
3. After the observation window, the same numbers are collected again. The window length has to
   match the baseline length or the comparison is meaningless; both default to three days.
4. The script compares them and prints a verdict: cheaper, more expensive, or inside the noise.

Progress is kept in a small state file, so the script can be scheduled and will stay silent
until the observation window has actually passed — a check that reports on itself every day is
a check I stop reading. The state file lives at `~/.hermes/data/compaction_experiment.json` by
default and contains four fields: the change timestamp, the observation deadline, the baseline
metrics, and a flag for "have I already printed the verdict". After the verdict prints once, the
flag goes to true, and the script is silent forever, until I start the next experiment.

The data the script reads comes from `~/.hermes/state.db`, the SQLite database where the agent
logs every model call — which model, how many input tokens, how many cache reads, the
estimated cost in dollars, and when the call was last seen. The script reads the
`session_model_usage` table, filters by timestamp window, and attributes the rows whose model
name contains `COMPACT_MODEL_NAME` to the compaction bill. Attribution is by name match on
purpose: I name the compaction model something distinctive (default `glm-5.3-flash`), so the
share of the bill that is compaction is the share whose row matches that name. If I use the
same model for both compaction and reasoning, I cannot tell the two apart — and that is one of
the limitations below.

## Quick start

```bash
export CHANGE_TIMESTAMP=$(date +%s)   # when the new policy went live
export COMPACT_MODEL_NAME="glm-5.3-flash"
export BASELINE_DAYS=3
export OBSERVE_DAYS=3

python3 compaction_effect_check.py
```

The first run records the baseline (it cannot compute a baseline without the timestamp of the
change, so it uses the days before that timestamp) and exits silently. The next three days of
runs do nothing — the observation window has not closed. On the day after that, the script
prints the verdict once and marks the state as reported. From then on, the script is silent
until I start a new experiment by changing the timestamp.

## Usage

Everything is configured through the environment, because the script is meant to run in cron
without arguments and without anyone at the keyboard:

- `HERMES_DB_PATH` — the usage database (default `~/.hermes/state.db`).
- `COMPACT_STATE_FILE` — the experiment state file (default
  `~/.hermes/data/compaction_experiment.json`).
- `BASELINE_DAYS` / `OBSERVE_DAYS` — window lengths in days (default 3 / 3).
- `COMPACT_MODEL_NAME` — the model that does the compacting, used to attribute its share of the
  spend (default `glm-5.3-flash`).
- `CHANGE_TIMESTAMP` — Unix timestamp of the policy change. This is the only required input,
  because everything else can be reconstructed from the state file once it exists.

Run it repeatedly (a daily cron is the natural place); it prints once, when there is something
to say. The natural cadence is: start a new experiment by editing the cron line and the
timestamp; let it run for a week; look at the verdict; if the change is worth keeping, commit
the new settings; if not, revert them and start a different experiment. The script does not
make any of those decisions — it only tells me what happened.

## Outputs

The verdict is four lines, in plain text, easy to paste into a chat or a note:

- daily cost, before against after;
- the compaction model's own cost and call count;
- the cache-to-input token ratio — the column where a "cheaper" policy usually turns out not
  to be;
- a verdict, in plain words, on whether the change is worth keeping.

The "verdict" line is the simple one. The cache-to-input ratio is the line that usually makes
the decision for me: if the cheaper model fires more often and breaks the cache prefix more
often, the daily cost goes up even though each call is cheaper. The compaction cost line tells
me whether the new compaction model is actually paying for itself; the call count tells me
whether the threshold change moved anything. I read all four every time, because the verdict
word ("better" or "worse") is just the most visible of the four signals.

## Limitations

- It reads a usage database. If the deployment does not record per-model usage, there is
  nothing to compare. The script does not invent numbers.
- Both windows have to contain a normal mix of traffic. A baseline that covers a weekend is not
  a baseline; my digests run weekdays and my health checks run hourly, and either pattern makes
  the comparison wrong if the window catches only one of them. I keep baseline and observation
  to the same length and the same day-of-week mix.
- Attribution is by model-name pattern, so two policies that use the same compaction model
  cannot be told apart — change one thing at a time. If I want to compare two threshold values,
  I keep the model the same; if I want to compare two models, I keep the threshold the same.
- The experiment assumes a single change inside the observation window. A second change during
  it invalidates the result, and the script cannot tell me that I made one. The discipline has
  to be mine.

The unit tests in `tests/test_compaction_effect_check.py` cover the bookkeeping that has to be
right for the verdict to mean anything: that the metrics function picks the right rows in the
right time range, that an already-reported experiment stays silent, and that an experiment
whose observation window has not passed stays silent. I run them whenever I touch the script;
the database and the state file are mocked, and the suite runs in a couple of seconds.

## Structure

```
├── compaction_effect_check.py  # main script
├── README.md                   # English documentation
├── README.ru.md                # Russian documentation
├── tests/
│   └── test_compaction_effect_check.py
└── examples/
    ├── sample_config.env       # example environment variables
    └── experiment_state.json   # example state file
```

The script is 135 lines, no external dependencies beyond the Python standard library
(`sqlite3`, `json`, `os`, `time`, `datetime`, `pathlib`). It runs on Python 3.10+. The
example state file in `examples/experiment_state.json` shows the four fields and the kind of
baseline numbers to expect; the example environment file in `examples/sample_config.env` shows
the names and the format of every variable the script reads.

## Related

- **35-context-compaction-engine** — the engine this check exists to accept: compaction by
  working state, judged by whether the task can still be continued. That engine is what I
  change; this script is how I know whether the change was worth it.
- **03-agent-ops-playbook** — the incident that turned context size from an annoyance into an
  operational topic. The playbook is where I write down what to do when the daily cost goes up
  unexpectedly; this script is the part that catches the "unexpectedly" early.

## License

MIT License - see the LICENSE file in the repository for details.