#!/usr/bin/env python3
"""Offline tests for janitor.py — builds throwaway skill libraries in a temp directory.

Run either way:
    python3 tests/test_janitor.py
    pytest tests/test_janitor.py
"""
import importlib.util
import io
import json
import contextlib
import pathlib
import sys
import tempfile

MODULE = pathlib.Path(__file__).resolve().parents[1] / "janitor.py"
spec = importlib.util.spec_from_file_location("janitor", MODULE)
janitor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(janitor)


def make_skill(root: pathlib.Path, name: str, body: str, description="Use when testing the janitor."):
    skill = root / name
    skill.mkdir(parents=True, exist_ok=True)
    front = f"---\nname: {name}\ndescription: {description}\n---\n\n"
    (skill / "SKILL.md").write_text(front + body, encoding="utf-8")
    return skill


def problems_for(result, needle):
    for item in result["findings"]:
        if needle in item["skill"]:
            return item["problems"]
    return []


def test_clean_library_has_no_findings(tmp_path):
    home = tmp_path / "home"
    (home / "scripts").mkdir(parents=True)
    (home / "scripts" / "helper.py").write_text("print('ok')\n", encoding="utf-8")
    make_skill(tmp_path / "skills", "good-skill",
               "Run `~/scripts/helper.py` and see `scripts/helper.py` in the library root.\n")
    result = janitor.audit_library([tmp_path / "skills"], home=home)
    assert result["checked"] == 1 and result["findings"] == []


def test_missing_path_and_script_are_reported(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    make_skill(tmp_path / "skills", "stale-skill",
               "See `~/.config/gone.json` and `scripts/absent.py`.\n")
    result = janitor.audit_library([tmp_path / "skills"], home=home)
    problems = problems_for(result, "stale-skill")
    assert any("missing path: ~/.config/gone.json" in p for p in problems)
    assert any("missing script: absent.py" in p for p in problems)


def test_paths_under_home_are_real_findings(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    make_skill(tmp_path / "skills", "docs-skill", "Read `~/docs/missing.md` for details.\n")
    result = janitor.audit_library([tmp_path / "skills"], home=home)
    assert result["external_paths_missing"] == 0  # under home -> a real finding, not "external"
    assert problems_for(result, "docs-skill")


def test_placeholders_are_ignored(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    make_skill(tmp_path / "skills", "template-skill",
               "Copy `~/projects/<name>/notes.md` and run `scripts/*.py`.\n")
    result = janitor.audit_library([tmp_path / "skills"], home=home)
    assert result["findings"] == []


def test_frontmatter_problems(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    make_skill(tmp_path / "skills", "short-desc", "Body.\n", description="too short")
    make_skill(tmp_path / "skills", "mismatch-dir", "Body.\n")
    (tmp_path / "skills" / "mismatch-dir" / "SKILL.md").write_text(
        "---\nname: other-name\ndescription: Use when the declared name drifts from the folder.\n---\n\nBody.\n",
        encoding="utf-8")
    result = janitor.audit_library([tmp_path / "skills"], home=home)
    assert any("description is 9 chars" in p for p in problems_for(result, "short-desc"))
    assert any("does not match directory" in p for p in problems_for(result, "mismatch-dir"))


def test_missing_frontmatter_is_reported(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    skill = tmp_path / "skills" / "no-front"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("Just prose, no frontmatter.\n", encoding="utf-8")
    result = janitor.audit_library([tmp_path / "skills"], home=home)
    problems = problems_for(result, "no-front")
    assert "frontmatter has no name" in problems and "frontmatter has no description" in problems


def test_syntax_errors_are_caught_and_can_be_skipped(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    skill = make_skill(tmp_path / "skills", "broken-code", "Runs `scripts/tool.py`.\n")
    (skill / "scripts").mkdir()
    (skill / "scripts" / "tool.py").write_text("def broken(:\n    pass\n", encoding="utf-8")
    with_code = janitor.audit_library([tmp_path / "skills"], home=home)
    assert any("syntax error" in p for p in problems_for(with_code, "broken-code"))
    without_code = janitor.audit_library([tmp_path / "skills"], home=home, check_syntax=False)
    assert not any("syntax error" in p for p in problems_for(without_code, "broken-code"))


def test_reported_lines_are_capped(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    skill = tmp_path / "skills" / "many"
    skill.mkdir(parents=True)
    body = "\n".join(f"`~/.gone/file{i}.json`" for i in range(40))
    (skill / "SKILL.md").write_text(
        "---\nname: many\ndescription: Use when many references are broken at once.\n---\n\n" + body,
        encoding="utf-8")
    result = janitor.audit_library([tmp_path / "skills"], home=home)
    assert len(problems_for(result, "many")) == 6


def test_report_text_is_empty_when_clean_and_lists_findings_when_not(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    make_skill(tmp_path / "skills", "good-skill", "Nothing referenced here.\n")
    clean = janitor.audit_library([tmp_path / "skills"], home=home)
    assert janitor.report_text(clean) == ""
    make_skill(tmp_path / "skills", "stale", "See `~/.config/gone.json`.\n")
    dirty = janitor.audit_library([tmp_path / "skills"], home=home)
    text = janitor.report_text(dirty)
    assert "need attention" in text and "stale" in text


def test_main_quiet_mode_and_strict_exit_code(tmp_path, capsys):
    home = tmp_path / "home"
    home.mkdir()
    make_skill(tmp_path / "skills", "good-skill", "Nothing referenced here.\n")
    code = janitor.main(["--skills-dir", str(tmp_path / "skills"), "--home", str(home), "--quiet"])
    assert code == 0 and capsys.readouterr().out == ""

    make_skill(tmp_path / "skills", "stale", "See `~/.config/gone.json`.\n")
    code = janitor.main(["--skills-dir", str(tmp_path / "skills"), "--home", str(home),
                         "--quiet", "--strict"])
    assert code == 1 and "stale" in capsys.readouterr().out


def test_main_writes_the_json_report(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    make_skill(tmp_path / "skills", "good-skill", "Nothing referenced here.\n")
    report = tmp_path / "report.json"
    janitor.main(["--skills-dir", str(tmp_path / "skills"), "--home", str(home),
                  "--report", str(report)])
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["checked"] == 1 and payload["findings"] == [] and "checked_at" in payload


if __name__ == "__main__":
    class _Capsys:
        """Minimal stand-in for pytest's capsys so the standalone run matches the pytest one."""

        def __init__(self):
            self._buffer = io.StringIO()

        def readouterr(self):
            # keeps one buffer object: redirect_stdout holds a reference to it, so swapping it
            # would send later output to a stream nothing reads (and pytest is not the issue here)
            out = self._buffer.getvalue()
            return type("Captured", (), {"out": out, "err": ""})()

    failures = 0
    tests = [(name, fn) for name, fn in sorted(globals().items())
             if name.startswith("test_") and callable(fn)]
    for name, fn in tests:
        tmp = pathlib.Path(tempfile.mkdtemp())
        capsys = _Capsys()
        try:
            params = fn.__code__.co_varnames[:fn.__code__.co_argcount]
            if "tmp_path" in params and "capsys" in params:
                with contextlib.redirect_stdout(capsys._buffer):
                    fn(tmp, capsys)
            elif "tmp_path" in params:
                fn(tmp)
            else:
                fn()
            print(f"ok   {name}")
        except Exception as exc:  # noqa: BLE001 - the runner reports and keeps going
            import traceback
            where = traceback.format_exc().strip().splitlines()[-2:]
            failures += 1
            print(f"FAIL {name}: {type(exc).__name__}: {exc}")
            for line in where:
                print(f"     {line.strip()}")
    print("all good" if not failures else f"{failures} failure(s)")
    raise SystemExit(1 if failures else 0)
