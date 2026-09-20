# 34 — skill-library-janitor

_Русская версия: [README.ru.md](README.ru.md)_

**A skill library does not fail loudly. A renamed file, a script that stopped compiling, a
frontmatter that lost its description — you find out in the middle of real work, when the skill
loads and the path it needs is gone.**

> Nothing here is clever: the tool walks the library and reports only what is checkably wrong. That
> is the point. It costs nothing to run monthly, it never calls a model, and it turns a class of
> silent rot into a short list you can act on. Wording, tone and usefulness are not its business.

## What you get

- `janitor.py` — walks every `SKILL.md` under one or more roots and reports broken references,
  code that does not compile, and frontmatter problems. Cron-friendly: `--quiet` prints nothing
  when the library is clean.
- `examples/sample-library/` — a three-skill library (one clean, one with stale references, one
  with a syntax error) and the recorded report the tool prints for it.
- `tests/test_janitor.py` — 11 offline tests that build throwaway libraries in a temp directory.

## What it checks

| Check | What it catches | Why it matters |
|---|---|---|
| Frontmatter | missing `name`/`description`, description outside 20–200 chars, `name` that drifted from the directory | the description is what a loader matches a task against; a drifted name breaks lookups |
| Referenced paths | `~/...`, absolute paths and `scripts/foo.py` mentions that no longer exist | the skill is loaded, then fails at the exact moment it is needed |
| Python syntax | files under the skill directory that no longer compile | an interpreter upgrade or a bad edit is invisible until run |
| Shell syntax | `.sh` files that fail `bash -n` | same, one step earlier |

## How to use it

```bash
python3 janitor.py --skills-dir ~/.hermes/skills --report janitor.json

# cron / monthly job: silent when clean, non-zero exit when dirty
python3 janitor.py --skills-dir ~/.hermes/skills --quiet --strict
```

`--skills-dir` takes several roots. `--home` sets what `~/` expands to (handy in tests and for
libraries outside your home directory). `--no-code` skips the compile steps for a fast frontmatter
and path pass.

## Output

```
$ python3 janitor.py --skills-dir examples/sample-library/skills --home examples/sample-library/home
skill library: 3 checked, 2 need attention (paths outside this machine, not counted as broken: 0)
- examples/sample-library/skills/endpoint-check: missing path: ~/.config/endpoints.json; missing script: legacy_ping.sh
- examples/sample-library/skills/weekly-report: collect.py: syntax error at line 4
```

`--report FILE` writes the same result as JSON with a timestamp, so a monthly job leaves a trace
of what it saw, not just of whether it complained.

## Calibration, so the report stays worth reading

- `scripts/foo.py` in a skill usually means the library-wide scripts directory, not a folder
  inside the skill. Three locations are tried before a reference is called broken; calling them
  broken by default is how a janitor gets muted.
- Paths with placeholders (`<name>`, `*.py`, `$VAR`, `~/.cache/…`) are skipped: they are patterns,
  not artefacts.
- A path that is missing outside the home tree is counted, not listed — those usually belong to
  other machines and other software, and are documentation rather than rot.
- Six findings per skill, so one broken skill cannot bury the rest.

## Limits

- It judges only what is checkable. A skill whose instructions are wrong but whose paths resolve
  passes.
- Python check is syntax only: imports, missing dependencies and dead endpoints are out of scope.
- It does not open the network. An endpoint that answered last month and is dead today is not its
  business — and it will not tell you that a nightly dependency upgrade broke something that still
  compiles.
- Run it on a schedule. A janitor that runs once proves nothing about the months after that.
