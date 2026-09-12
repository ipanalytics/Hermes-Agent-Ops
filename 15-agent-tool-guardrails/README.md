# 15 — agent-tool-guardrails

**Stop trusting the agent's own report: gate the commands, vet the skills, and let the orchestrator accept the work.**

> Two failure modes. First: a destructive command goes through because the approval layer
> greps the text for scary words — `r''m -rf /`, `$(...)`, `bash -c "..."` and
> `base64 -d | sh` all walk past a regex. Second: several writers share one checkout and the
> only evidence is the writer's sentence "done, tests pass."

## What you get here

| Artifact | Job | Tests |
|---|---|---|
| `hooks/bash_guard.py` + `hooks/policy.json` | `pre_tool_call` gate: parses the command, then judges it | `tests/test_bash_guard.py` — 22 cases |
| `hooks/skill_scan.py` | vet a skill / prompt / agent config before it is trusted | exercised against a canary malicious skill |
| `lanes.py` | one git worktree per writer + an acceptance gate with evidence | `tests/test_lanes.py` — 16 checks |
| `install.sh` | copy the hooks into `$HERMES_HOME` and register them | — |

Everything is stdlib Python. The only dependency is `bashlex` (pure-python wheel), vendored
into `$HERMES_HOME/pylibs` so the hook never depends on the agent's own virtualenv.

## Why parsing beats grepping

`bash_guard` walks the AST instead of scanning the string, so nested payloads are real
commands to it, and normalising quote/backslash runs makes `r''m -rf /` read as `rm -rf /`.
Rules are structural: recursive delete of a system root, `--no-preserve-root`, `dd of=/dev/sd*`,
`mkfs`/`wipefs`, fork bombs, decoder-into-shell (`base64 -d … | sh`), a credential store
combined with a network tool in the same command, writes to `/etc/shadow`, `sudoers`, `.env`,
`auth.json`, `authorized_keys`, and `qm|pct destroy|stop|reset` against a VM id you list as
protected. Two tiers: **block** (destructive, reported back to the agent as a refusal) and
**flag** (logged only — `curl … | bash` installers and `pip install` are normal work).

```bash
python3 hooks/bash_guard.py < payload.json     # hook contract: stdin JSON -> stdout block JSON
python3 tests/test_bash_guard.py               # 22 cases, includes the quote/bidi evasions
```

Register it (never hand-edit `config.yaml`):

```bash
hermes config set hooks_auto_accept true
hermes config set hooks '{"pre_tool_call":[{"matcher":"terminal","command":"/usr/bin/python3 '"$PWD"'/hooks/bash_guard.py","timeout":10,"fail_closed":true}]}'
hermes gateway restart        # hooks bind at process start; new CLI runs pick them up at once
```

**Verify end-to-end, not just with unit tests.** Put a canary regex in `policy.json`
(`"block_patterns": ["CANARY_GUARD_TEST"]`) and run
`hermes chat -q "run exactly: echo CANARY_GUARD_TEST"`. The agent must report the refusal.
Never validate a gate with a genuinely destructive command — if the gate is broken, the
command really runs.

## Vetting skills before they teach your agent

A skill is executable policy written by a stranger: prompt-injection framing, zero-width and
bidi characters that never render in a diff, credential-store reads, drop-box webhooks,
`curl | bash`, decoders piped into a shell.

```bash
python3 hooks/skill_scan.py path/to/skill          # human report, exit 2 on any HIGH
python3 hooks/skill_scan.py --all-installed        # audit the whole library
python3 hooks/skill_scan.py --hook                 # pre_tool_call mode: block the install
```

Context beats any single pattern. A lone mention of `~/.ssh/id_...` appears in every SSH
tutorial, so a secret path alone is **MEDIUM** and escalates to **HIGH** only when the same
file also carries an egress path; `curl | bash` against a documented installer stays MEDIUM.
Library audit with these rules: 546 files, 28 HIGH before the combination rules, after them
almost all remaining HIGH hits are legitimate documentation quoting `~/.hermes/.env`. Expect
false positives on your own docs; review them instead of forking the rules per file. The repository's own test corpus will flag itself
(attack strings are the fixtures); that is expected.

## Lanes: parallel writers, one acceptance gate

```bash
lanes.py new    REPO lane-a lane-b        # worktrees under REPO/.worktrees/, branches lane/<name>
lanes.py status REPO --json               # commits ahead, dirty files, diff stat per lane
lanes.py gate   REPO [lanes...] --cmd "python3 -m pytest -q"
lanes.py merge  REPO --into integration   # serial merge, aborts on conflict
lanes.py report REPO                      # evidence JSON: heads, diffs, gate results
```

The orchestrator re-runs the verification inside each lane and closes the card with a commit
id and a command's exit code, not with a worker's self-report. A red
lane is not merged; a conflict aborts the merge and leaves the lane isolated.

Three details that only appear when two writers run at once, all learned by breaking them:

- Inside a lane, `HEAD` is the **lane's** tip — the baseline must come from the main
  checkout, or every lane reports zero commits.
- Lane hygiene belongs in `.git/info/exclude`, not `.gitignore`; otherwise `new` leaves an
  uncommitted file and every later "is the tree clean?" check fails.
- Parse status with `git diff --name-only` / `git ls-files --others`. Slicing porcelain
  columns silently truncates names (`app.py` → `pp.py`).

## Related modules

Continues **02** (process supervision — same "judge from outside" stance, now for commands
and worktrees) and **07** (the linter that guards prompts before they ship; this guards what
the agent does with them). The lane/evidence halves pair with Hermes' own
`delegation.worktree_isolation` and kanban worker lanes.
