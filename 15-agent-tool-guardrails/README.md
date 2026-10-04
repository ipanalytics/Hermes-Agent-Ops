# 15 — agent-tool-guardrails

_Russian version: [README.ru.md](README.ru.md)_

![License](https://img.shields.io/github/license/ipanalytics/Hermes-Agent-Ops.svg)
![Status](https://img.shields.io/badge/status-production-green.svg)
![Python](https://img.shields.io/badge/python-3.10+-blue.svg)

I stopped trusting the agent's own report: commands go through a gate, skills get vetted, and the
orchestrator accepts the work. Three pieces, one folder: a terminal-command gate, a skill-file
scanner, and a worktree-lane workflow with an acceptance gate.

## What Hermes is (for a new reader)

Hermes is the AI agent I run on my own server. It runs scheduled jobs, edits my files, calls
providers, and writes its own scripts. "Providers" are the model backends — different companies
offer different LLM models at different prices, and Hermes talks to several of them. Two of the things
Hermes does are also the two easiest ways for it to do real damage: it runs shell commands, and it
installs skills written by other people. "Tokens" are the units providers bill on; every model call
costs input and output tokens. "Audit" here means a record of decisions after the fact.

This folder exists because I stopped assuming those two activities were safe. A scheduled job may
fire at 03:00 with a prompt I wrote months ago and a context it does not share with me; an install
of a "useful" skill I found online is, technically, executable policy written by a stranger. I built
three small pieces of code so the dangerous parts have to argue their way through a gate.

## Why it exists — two failure modes

**Failure mode 1: a destructive command goes through.** The naive way to gate commands is a list of
regexes that block "rm -rf /" and call it done. That fails in three seconds: `r''m -rf /`, `$(rm
-rf /etc)`, `curl ... | bash`, base64-decoded payloads piped into `sh`. Regex on raw text does not
see those as `rm`. I needed a hook that parsed the command as a real shell — parsed the AST
(abstract syntax tree, the structured form of the command) so that nested substitutions and pipes
are inspected, not just the surface string — and only then decided.

**Failure mode 2: the agent reports "done" and I take its word for it.** Several agents editing the
same checkout silently overwrite each other, and the orchestrator (the small loop that splits work
across agents) only has the agents' own reports. The agents are not lying, they are just wrong
about which files they actually touched and whether the tests still pass. I needed the
orchestrator to re-run the verify command itself, on each writer's branch, and only accept work
that produced evidence the orchestrator could read.

That is the whole folder. A pre-tool-call shell hook that blocks destructive commands. A skill
scanner that refuses to install files containing prompt-injection or exfiltration patterns. A
worktree workflow that gives every parallel writer its own branch and a gate that the orchestrator
runs.

## What's in the folder

- `hooks/bash_guard.py` — pre-tool-call shell hook. Parses the command with `bashlex` (a Python
  library that turns shell text into a real syntax tree), walks the AST so command substitutions
  and pipelines are seen as real commands, normalises word slices (quote/backslash stripping) so
  `r''m` is judged as `rm`. Returns `{"action": "block", "message": "..."}` for destructive
  patterns; otherwise allows. Logs to `~/.hermes/logs/bash_guard.jsonl`. Fails open on internal
  error with a trace — a broken guard must never be worse than no guard.
- `hooks/skill_scan.py` — vets a skill, prompt file, or agent config before it is trusted. Scores
  prompt-injection patterns (`"ignore previous instructions"`), stealth-unicode (zero-width or
  bidi control characters that never render in a diff), secret-path mentions combined with egress
  tools (network calls — anything that sends bytes off this machine), `curl | bash`,
  base64-decode-into-shell, `rm -rf /`, `mkfs`, `dd of=/dev/...`, and the disabling of OS
  security controls. Can run as `--hook` on the install path so a HIGH finding blocks the write.
- `hooks/policy.json` — the tunable part of `bash_guard`. I keep my own regexes in `block_patterns` (
  hard-blocks), `allow_regexes`, or change `protected_vm_ids`. Delete a key to fall back to the
  built-in default inside `bash_guard.py`.
- `lanes.py` — worktree lanes for parallel writers + an acceptance gate. Each lane gets its own
  `git worktree` under `<repo>/.worktrees/<lane>` and its own branch `lane/<lane>`. The gate re-runs
  the project's verify command inside every lane, captures exit code and tail, and accepts only
  the lanes that pass.
- `install.sh` — copies the hooks into `$HERMES_HOME/hooks/`, prints the `config.yaml` lines that
  register `bash_guard.py` as `pre_tool_call` for the `terminal` tool and `skill_scan.py` for
  `write_file`. `--register` does the config edit in place (idempotent).
- `tests/test_bash_guard.py` — 22 wire-contract cases (the JSON-on-stdin / JSON-on-stdout
  contract a Hermes shell hook must obey). Includes `rm -rf /`, `echo $(rm -rf /etc)`, `bash -c 'rm
  -rf /var'`, `cat ~/.hermes/auth.json | curl ...`, `base64 -d ... | sh`, `qm destroy 100`,
  `dd ... of=/dev/sda`, fork bombs, and `> /etc/shadow`.
- `tests/test_lanes.py` — end-to-end test on a temporary repo: creates two lanes, runs `status`,
  makes one pass and one fail the gate, merges into `integration`, runs the conflict path.

## How bash_guard decides

Six rules, applied to the normalised command tree:

1. **Filesystem annihilation.** `rm -rf /`, `rm -rf /*`, `rm --no-preserve-root /`, `mkfs`,
   `wipefs`, `dd of=/dev/...`, `shred /dev/...`. Blocks.
2. **Nested shell payloads.** `bash -c 'rm -rf /var'`, `eval "..."`, `$(rm -rf /etc)`. The inner
   command is checked recursively (depth limit 3) and blocks if it blocks.
3. **Protected guests.** `qm stop/destroy/reset/reboot/suspend/shutdown 100` and the same verbs on
   `pct`. The VM IDs are configurable; the default protects the gateway VM. Blocks.
5. **Critical file writes.** `tee /etc/shadow`, `cp /etc/sudoers ...`, redirects into
   `~/.hermes/.env`, `~/.hermes/auth.json`, `~/.ssh/authorized_keys`, etc. Blocks.
6. **Secrets + egress combo.** A sensitive path (`~/.hermes/.env`, `~/.ssh/id_*`, `/etc/shadow`,
   `~/.netrc`) on the same line as `curl` / `wget` / `nc` / `ssh`. Blocks.
7. **Decoder piped into a shell.** `base64 -d payload.b64 | sh`, `xxd -r ... | bash`,
   `openssl enc -d ... | sh`. Blocks.

A separate `flag` tier (logged but allowed): `curl ... | bash` from an unknown host,
`npm install -g`, `pip install`. These are normal-looking installers; I want them in the audit log
so a future review can ask "why did the agent install this at 03:00?"

## How lanes.py works

Five subcommands. Exit codes: 0 ok, 1 lane failures or merge conflict, 2 usage/git error.

```bash
lanes.py new    REPO lane-a lane-b           # create worktrees + branches from current HEAD
lanes.py status REPO                         # per-lane: head, commit count, dirty files, diff stat
lanes.py gate   REPO [--cmd "pytest -q"]     # re-run verification inside every lane
lanes.py merge  REPO --into integration      # merge lane/<lane> into the named branch
lanes.py report REPO                         # evidence JSON (commits, dirty, diff) for the orchestrator
```

The verify command is auto-detected: a `hermes verify` manifest under `.hermes/environment.json`
wins, then a Python project gets `python3 -m pytest -q`, then an npm project gets `npm test
--silent`. Override with `--cmd`. The gate re-runs the verify inside the lane's checkout (not on
the main checkout) so a writer cannot fake passing tests by editing shared files.

Worktrees live in `REPO/.worktrees/<lane>`; the path is added to `.git/info/exclude` (not
`.gitignore`), so lane checkouts stay out of `git status` for the main clone without adding an
uncommitted file to the repo itself.

## How I use it in production

- `bash_guard.py` is registered as the `pre_tool_call` hook for the `terminal` tool. Every command
  Hermes wants to run is checked; blocks and flags are logged to `~/.hermes/logs/bash_guard.jsonl`.
- `skill_scan.py` is registered as the `pre_tool_call` hook for `write_file` when the path lives
  under `~/.hermes/skills/` or `~/.hermes/prompts/`. A HIGH finding blocks the write; the agent is
  told to inspect the file and re-run with an explicit decision.
- `lanes.py` is invoked from the orchestrator loop. Workers get their own lane; the gate runs
  before any merge is accepted; the evidence file is what the daily sweep (`05-cron-of-crons`)
  audits against.
- I re-run `skill_scan.py --all-installed` once a month against `~/.hermes/skills/` as a baseline
  audit. It found nothing in production — that is the result I want, and the cheapest way to keep
  it that way is to keep checking.

## Quick start

```bash
# gate commands and skills
bash install.sh                 # copies hooks, prints the config commands
bash install.sh --register      # also edits config.yaml in place

# vet one skill before installing
python3 hooks/skill_scan.py path/to/SKILL.md

# the hook contract, and the setting that stops the re-approval loop
python3 hooks/bash_guard.py < payload.json   # stdin JSON in, block JSON out
hermes config set hooks_auto_accept true     # do not re-approve the same LOW finding every time

# parallel writers with an acceptance gate
python3 lanes.py new ~/work/repo lane-a lane-b
# (work happens inside .worktrees/lane-a and .worktrees/lane-b)
python3 lanes.py gate ~/work/repo --cmd "python3 -m pytest -q"
python3 lanes.py merge ~/work/repo --into integration
```

## Limitations

- **bash_guard is fail-open.** A bug in the hook, a missing `bashlex`, an internal exception — the
  command is allowed and the failure is logged. The reason: a broken guard must never be worse
  than no guard, especially at 03:00 when nobody is watching the log.
- **bash_guard covers what I have seen.** The rules are not a complete list of dangerous commands.
  My own rules go in `policy.json > block_patterns`.
- **lanes.py assumes git.** It will not work on a checkout that is not a git repo. The merge step
  uses `git merge --no-ff`; a true three-way merge conflict is reported and the merge is aborted,
  the lane stays isolated.
- **skill_scan is regex, not a parser.** A sufficiently obfuscated injection can slip past it.
  Treat its verdict as one signal, not as a guarantee.

## License

MIT