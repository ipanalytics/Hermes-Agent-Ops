# 34 — skill-library-janitor

_Russian version: [README.ru.md](README.ru.md)_

**Hermes is a home AI agent I run on my own server. Most of the work it does is scheduled: a cron job is a task the system starts on its own at a set time — every hour, every morning, the first Sunday of the month — with no human in the loop. To know what to do, the agent reads a folder of "skills": small markdown files, one per recurring task. A skill is just a `SKILL.md` with a YAML header at the top (called frontmatter) and a prose body. The header carries a `name` and a short `description`; the body tells the agent which script to run, which file to read, which pattern to look for. The folder of those files is the library. The library is what I trust, so I want it to be honest.**

**A skill library does not fail loudly. A file the skill points at gets renamed during a refactor. A script stops compiling after a Python upgrade. The `description` field gets truncated to four characters and the loader stops matching tasks to the skill. The directory is renamed and the `name` in the header does not follow. None of this throws an error at write time, because nothing is being executed yet. I find out in the middle of real work — when the skill is loaded and the path it needs is gone, or the script blows up on the first import, or the agent never even considers the skill because the description is empty.**

> The janitor in this folder is the fix. It walks the library, reads every `SKILL.md`, and reports only what is checkably wrong: broken references, code that no longer compiles, frontmatter that is missing or out of bounds. It costs nothing to run monthly because it never calls a model — it just reads files from disk and runs `bash -n` on shell scripts. Wording, tone and usefulness of each skill are not its business; those are mine.

## What's in here

- `janitor.py` — walks every `SKILL.md` under one or more roots and reports broken references, code that does not compile, and frontmatter problems. Cron-friendly: `--quiet` prints nothing when the library is clean, `--strict` exits with code 1 when findings exist, so a monthly job can fail the run and wake me up.
- `examples/sample-library/` — a three-skill library: one clean (`release-notes`), one with stale references (`endpoint-check`), one with a Python syntax error (`weekly-report`), plus `report.txt` — the exact thing the tool prints when it scans them. Useful as a worked example when I want to remember what each finding type looks like without running anything.
- `tests/test_janitor.py` — 11 offline tests that build throwaway libraries in a temp directory. They cover a clean library, a stale one, a placeholder-only one, a syntax-broken one, a many-findings one (to prove the 6-per-skill cap), the quiet/strict/report CLI flags, and the frontmatter edge cases. They run with either `pytest` or as a plain script.

## What it checks

The tool splits each `SKILL.md` into a frontmatter block (the `---`-delimited YAML at the top, where `name:` and `description:` live) and a body, then runs four kinds of check. The first three are static — they only read text from disk. The fourth shells out to `bash -n` for `.sh` files.

| Check | What it catches | Why it matters |
|---|---|---|
| Frontmatter | missing `name` or `description`, description outside 20–200 chars, `name` that drifted from the directory name | the description is what a loader matches a task against. If it is empty, too short, or too long, the loader never picks the skill — and I get a "Hermes did not know how to do X" silence instead of an answer. A drifted `name` breaks lookups that compare it to the folder |
| Referenced paths | `~/...`, absolute paths and `scripts/foo.py` mentions that no longer exist on disk | the skill is loaded, then dies at the exact moment it is needed — usually when I am already late for whatever the skill was supposed to do |
| Python syntax | every `.py` under the skill directory that does not compile | an interpreter upgrade or a bad edit is invisible until the script runs; the agent catches it once, the whole skill stops being trusted, and I never get a clear "this is broken" message |
| Shell syntax | every `.sh` that fails `bash -n` | same, one step earlier — caught before the agent ever tries to execute it |

Each finding is one short line: a path or a filename, prefixed with `missing path:`, `missing script:` or `syntax error at line N`. Short on purpose, because the report is meant to be skimmable on a phone while I am not at the keyboard.

## How I use it

```bash
python3 janitor.py --skills-dir ~/.hermes/skills --report janitor.json

# cron / monthly job: silent when clean, non-zero exit when dirty
python3 janitor.py --skills-dir ~/.hermes/skills --quiet --strict
```

`--skills-dir` takes several roots, repeatable — I pass `~/.hermes/skills` plus any plugin-local skill folder I want included in the same audit, in one invocation. `--home` sets what `~/` expands to, which is handy in tests and for libraries that live outside the home directory (CI, a removable mount, a forked copy on another machine). `--no-code` skips the Python and shell compile steps and does only the frontmatter and path pass — useful when I just want to know which skills point at files that no longer exist, and the syntax check would take longer.

`--quiet` is the cron mode: when the library is clean, nothing is printed and the exit code is 0; when something is wrong, the report is still printed, and (with `--strict`) the exit code becomes 1, so a wrapping cron job can alert me. `--report FILE` writes the same result as JSON with a Unix timestamp, so a monthly job leaves a trace of what it actually saw — not just of whether it complained. That history is what lets me tell "this skill has been failing since March" from "this is a fresh one".

The lines that come out look like this:

```
$ python3 janitor.py --skills-dir examples/sample-library/skills --home examples/sample-library/home
skill library: 3 checked, 2 need attention (paths outside this machine, not counted as broken: 0)
- examples/sample-library/skills/endpoint-check: missing path: ~/.config/endpoints.json; missing script: legacy_ping.sh
- examples/sample-library/skills/weekly-report: collect.py: syntax error at line 4
```

Two findings on one line each, plus a header line with the totals and the count of paths the tool saw as missing but did not count as broken (more on that rule below). Exit code is 0 here because I did not pass `--strict` — the report is printed either way, but only `--strict` turns "dirty" into a non-zero exit.

## Calibration, so the report stays worth reading

A janitor that cries wolf gets muted. Four rules keep the report honest:

- `scripts/foo.py` in a skill usually means the library-wide scripts directory, not a folder inside the skill itself. Before a reference is called broken, three locations are tried in order: `<skill_dir>/scripts/foo.py`, then `<skill_dir>/foo.py`, then `<home>/scripts/foo.py`. Calling such a reference broken by default is how the janitor gets disabled within a week.
- Paths with placeholders are skipped. Anything containing `*`, `{`, `}`, `<`, `>`, an ellipsis (`…`), a bare `N` or `X`, or a `$` is treated as a pattern in the prose, not an artefact to look for on disk. Reporting those as broken would flag every skill that uses an example path or a templated config key.
- A path that is missing outside the home tree is counted, not listed. The header line ends with `(paths outside this machine, not counted as broken: N)`. Those usually belong to other machines, other software, or other users — the agent does not run there, so they are documentation about the world, not rot in my library.
- Six findings per skill, max. If one skill has forty broken references after a refactor, the others still get reported. Without the cap, one bad migration would bury every other problem in the report and I would stop reading.

These are not configurable, by the way. They are calibrated to the shape of my skills and the kind of mistakes I actually make; tightening them would make the janitor noisy, loosening them would make it useless.

## Limits

- It judges only what is checkable. A skill whose instructions are wrong but whose paths resolve and whose description is well-formed passes. Catching bad prose is not what a janitor does.
- The Python check is syntax only: `compile()` runs against the file, nothing more. Imports that fail, missing dependencies, dead HTTP endpoints, runtime errors — all out of scope.
- The shell check is `bash -n` only. A `.sh` script that always `exit 0` without doing anything passes.
- It does not open the network. An endpoint that answered last month and is dead today is not its business — and it will not tell me that a nightly dependency upgrade broke something that still parses and still imports cleanly.
- Run it on a schedule. A janitor that runs once proves nothing about the months after that. The whole point of this folder is the audit that catches drift six weeks from now, not the one I ran today to convince myself the tool works.