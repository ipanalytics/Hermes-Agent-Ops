#!/usr/bin/env python3
"""bash_guard — AST-based terminal command guard for Hermes (pre_tool_call shell hook).

Why: approval decisions on raw regexes are trivially evaded (`r''m -rf /`, `$(...)`,
pipes, base64 decoders). This hook parses the command with bashlex, walks the AST so
nested command substitutions/pipelines are seen as real commands, and normalises word
slices (quote/backslash stripping) so `r''m` is judged as `rm`.

Contract (Hermes shell hooks, event pre_tool_call):
  stdin : {"hook_event_name": "pre_tool_call", "tool_name": "terminal",
           "tool_input": {"command": "..."}, "cwd": "...", "session_id": "..."}
  stdout: {"action": "block", "message": "..."}  -> tool call rejected
          nothing / {}                            -> allow

Never raises: any internal error logs and allows (fail-open). Policy lives in
policy.json next to this file.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
HERMES_HOME = os.environ.get("HERMES_HOME") or os.path.join(os.path.expanduser("~"), ".hermes")
# bashlex ships as a pure-python wheel; vendoring it into $HERMES_HOME/pylibs keeps the
# hook dependency-free from the agent's own virtualenv.
PYLIBS = os.path.join(HERMES_HOME, "pylibs")
LOG_PATH = os.path.join(HERMES_HOME, "logs", "bash_guard.jsonl")

if os.path.isdir(PYLIBS) and PYLIBS not in sys.path:
    sys.path.insert(0, PYLIBS)

try:
    import bashlex  # noqa: F401
    import bashlex.ast as bashlex_ast
    _HAVE_BASHLEX = True
    _BASHLEX_ERR = ""
except Exception as exc:  # pragma: no cover - env dependent
    bashlex = None
    bashlex_ast = None
    _HAVE_BASHLEX = False
    _BASHLEX_ERR = f"{type(exc).__name__}: {exc}"

# ── policy ────────────────────────────────────────────────────────────────────
DEFAULT_POLICY = {
    "roots": ["/", "/*", "/etc", "/usr", "/var", "/boot", "/home", "/root", "/opt", "/srv",
              "/dev", "~", "$HOME", "${HOME}"],
    "protected_vm_ids": ["100"],
    "vm_control_cmds": ["stop", "destroy", "reset", "reboot", "suspend", "shutdown"],
    "sensitive_paths": [
        r"\.hermes/\.env", r"\.hermes/auth\.json", r"\.hermes/shell-hooks-allowlist\.json",
        r"\.ssh/id_[A-Za-z0-9]+", r"\.ssh/authorized_keys", r"/etc/shadow", r"/etc/sudoers",
        r"\.aws/credentials", r"\.netrc", r"\.config/gh/hosts\.yml",
    ],
    "critical_write_paths": [
        r"/etc/passwd$", r"/etc/shadow$", r"/etc/sudoers$", r"\.ssh/authorized_keys$",
        r"\.hermes/\.env$", r"\.hermes/auth\.json$", r"\.hermes/config\.yaml$",
        r"\.hermes/shell-hooks-allowlist\.json$",
    ],
    "egress_tools": ["curl", "wget", "nc", "ncat", "socat", "ssh", "scp", "sftp", "rsync",
                     "telnet", "ftp", "lynx"],
    "decoders": [r"base64\b", r"\bxxd\b", r"openssl\s+enc\s+-d", r"\brev\b", r"\buudecode\b"],
    "shells": ["sh", "bash", "zsh", "dash", "ksh"],
    "flag_patterns": [
        r"curl[^|]*\|\s*(?:sudo\s+)?(?:sh|bash|zsh)\b",
        r"wget[^|]*\|\s*(?:sudo\s+)?(?:sh|bash|zsh)\b",
        r"npm\s+install\s+-g", r"pip\s+install\b",
    ],
    "allow_regexes": [],
    "log_all": False,
}


def _load_policy() -> dict:
    policy = dict(DEFAULT_POLICY)
    path = os.path.join(HERE, "policy.json")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            user = json.load(fh)
        if isinstance(user, dict):
            policy.update(user)
    except FileNotFoundError:
        pass
    except Exception as exc:
        _log({"decision": "warn", "rule": "policy-load", "detail": str(exc)})
    return policy


# ── AST extraction ────────────────────────────────────────────────────────────
def _is_node(obj) -> bool:
    return _HAVE_BASHLEX and isinstance(obj, bashlex_ast.node)


def _walk(node, out):
    """Collect every node in the tree (bashlex nodes nest via many attribute names)."""
    out.append(node)
    try:
        for value in vars(node).values():
            if _is_node(value):
                _walk(value, out)
            elif isinstance(value, list):
                for item in value:
                    if _is_node(item):
                        _walk(item, out)
    except Exception:
        pass


def _norm(text: str) -> str:
    """Strip quote/backslash obfuscation: r''m -> rm, \\rm -> rm."""
    return re.sub(r"\\?(['\"])", "", text)


def _word_text(raw: str, node) -> str:
    pos = getattr(node, "pos", None)
    if isinstance(pos, tuple) and len(pos) == 2:
        try:
            return raw[pos[0]:pos[1]]
        except Exception:
            return ""
    return ""


def extract(raw_command: str) -> dict:
    """Return {"commands": [{"argv": [...], "raw": "..."}], "pipes": [[argv,...],...],
    "redirects": ["path", ...], "text": "<normalised full command>", "parsed": bool}."""
    result = {"commands": [], "pipes": [], "redirects": [], "text": _norm(raw_command),
              "parsed": False}
    if not _HAVE_BASHLEX:
        return result
    try:
        trees = bashlex.parse(raw_command)
    except Exception:
        return result
    result["parsed"] = True
    nodes = []
    for tree in trees:
        _walk(tree, nodes)
    for node in nodes:
        kind = getattr(node, "kind", None)
        if kind == "command":
            argv = []
            for part in getattr(node, "parts", []) or []:
                if getattr(part, "kind", None) == "word":
                    argv.append(_word_text(raw_command, part))
                elif getattr(part, "kind", None) == "assignment":
                    argv.append(_word_text(raw_command, part))
            if argv:
                result["commands"].append({"argv": [_norm(a) for a in argv],
                                           "raw": " ".join(argv)})
        elif kind == "pipeline":
            stages = []
            for part in getattr(node, "parts", []) or []:
                if getattr(part, "kind", None) == "command":
                    argv = []
                    for sub in getattr(part, "parts", []) or []:
                        if getattr(sub, "kind", None) in ("word", "assignment"):
                            argv.append(_norm(_word_text(raw_command, sub)))
                    if argv:
                        stages.append(argv)
            if stages:
                result["pipes"].append(stages)
        elif kind == "redirect":
            for attr in ("output", "input"):
                target = getattr(node, attr, None)
                if target is None:
                    continue
                text = _word_text(raw_command, target) if _is_node(target) else str(target)
                if text:
                    result["redirects"].append(_norm(text))
    # Every command in a pipeline stage is also a command.
    for stages in result["pipes"]:
        for argv in stages:
            result["commands"].append({"argv": argv, "raw": " ".join(argv)})
    return result


# ── rules ─────────────────────────────────────────────────────────────────────
def _basename(cmd: str) -> str:
    return os.path.basename(cmd.strip()) if cmd else ""


def _strip_quotes(text: str) -> str:
    return text.strip().strip("'\"")


def check(command: str, policy: dict, depth: int = 0) -> tuple[str, str, str]:
    """Return (decision, rule, message). decision in {allow, flag, block}."""
    info = extract(command)
    text = info["text"]
    lowered = text.lower()

    for pattern in policy.get("block_patterns", []):
        try:
            if re.search(pattern, text):
                return "block", "custom-policy", f"custom block pattern matched: {pattern}"
        except re.error:
            continue

    for pattern in policy.get("allow_regexes", []):
        try:
            if re.search(pattern, text):
                return "allow", "allow-regex", ""
        except re.error:
            continue

    for cmd in info["commands"]:
        argv = cmd["argv"]
        if not argv:
            continue
        name = _basename(_strip_quotes(argv[0]))
        args = [_strip_quotes(a) for a in argv[1:]]

        # 1) filesystem annihilation
        if name == "rm":
            recursive = any(a.startswith("-") and not a.startswith("--") and
                            ("r" in a[1:].lower() or "R" in a[1:]) for a in args) or \
                        any(a in ("--recursive", "-r", "-R", "-rf", "-fr") for a in args)
            targets = [a for a in args if not a.startswith("-")]
            for target in targets:
                if "no-preserve-root" in lowered:
                    return "block", "rm-no-preserve-root", f"rm --no-preserve-root on {target}"
                if target in policy["roots"] or target.rstrip("/") in (
                        r.rstrip("/") for r in policy["roots"]):
                    if recursive or target in ("/", "/*"):
                        return ("block", "rm-system-root",
                                f"recursive delete of system root: rm on {target}")
        if name in ("mkfs", "wipefs", "shred", "fdisk", "parted") or name.startswith("mkfs."):
            if name == "shred" and not any(a.startswith("/dev/") for a in args):
                continue
            return "block", "disk-destroy", f"disk/filesystem destroyer: {name}"
        if name == "dd":
            if any(a.startswith("of=/dev/") for a in args):
                return "block", "dd-to-device", "dd writing to a raw block device"

        # 1b) nested shell payloads: bash -c "rm -rf /", eval "..."
        if name in policy["shells"] or name == "eval":
            inner = " ".join(args[1:] if args[:1] == ["-c"] else args)
            if inner.strip() and depth < 3:
                sub_decision, sub_rule, sub_msg = check(inner, policy, depth + 1)
                if sub_decision == "block":
                    return ("block", f"nested:{sub_rule}",
                            f"nested shell payload ({name} -c) — {sub_msg}")

        # 2) protected guests
        if name in ("qm", "pct"):
            verb = args[0].lower() if args else ""
            ids = [a for a in args[1:] if a.isdigit()]
            if verb in policy["vm_control_cmds"] and any(i in policy["protected_vm_ids"] for i in ids):
                return ("block", "protected-vm",
                        f"{name} {verb} on protected VM {', '.join(ids)}")

        # 3) critical file writes / permission rewrites
        if name in ("chmod", "chown") and any(a.startswith("-R") or a.startswith("--recursive")
                                              for a in args):
            if any(_strip_quotes(a).rstrip("/") in ("/", "/*") for a in args):
                return "block", "recursive-root-chmod", f"recursive {name} on /"
        if name in ("tee", "cp", "mv", "install", "truncate") or name in ("sed", "perl"):
            for arg in args:
                for pattern in policy["critical_write_paths"]:
                    if re.search(pattern, arg) and name != "sed":
                        return ("block", "critical-file-write",
                                f"{name} writing to protected file: {arg}")

    for target in info["redirects"]:
        for pattern in policy["critical_write_paths"]:
            if re.search(pattern, target):
                return "block", "critical-file-redirect", f"redirect overwriting {target}"

    # 4) sensitive file + network egress in the same command line
    if re.search(r":\s*\(\s*\)\s*\{.*\|.*&.*\}|:\(\)\{\s*:\|:&\s*\};:", lowered):
        return "block", "fork-bomb", "fork bomb"

    sensitive = [p for p in policy["sensitive_paths"] if re.search(p, text)]
    if sensitive:
        for cmd in info["commands"]:
            if cmd["argv"] and _basename(_strip_quotes(cmd["argv"][0])) in policy["egress_tools"]:
                return ("block", "secret-exfiltration",
                        f"secret path ({sensitive[0]}) combined with network tool "
                        f"{_basename(cmd['argv'][0])}")

    # 5) decoder piped into a shell (classic obfuscation)
    for stages in info["pipes"]:
        names = [_basename(_strip_quotes(s[0])) for s in stages if s]
        if names and names[-1] in policy["shells"]:
            joined = " ".join(" ".join(s) for s in stages[:-1])
            if any(re.search(d, joined) for d in policy["decoders"]):
                return ("block", "decoder-pipe-shell",
                        "encoded payload piped into a shell "

                        f"({' | '.join(names)})")

    # 6) flags — logged, not blocked (legit installs look like this)
    for pattern in policy.get("flag_patterns", []):
        if re.search(pattern, text):
            return "flag", "flagged-pattern", f"matched pattern: {pattern}"

    if policy.get("log_all"):
        return "allow", "log-all", ""
    return "allow", "", ""


def _log(entry: dict) -> None:
    try:
        entry = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), **entry}
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    try:
        if payload.get("hook_event_name") not in (None, "pre_tool_call"):
            return 0
        tool_input = payload.get("tool_input") or {}
        command = tool_input.get("command") or tool_input.get("cmd") or ""
        if not isinstance(command, str) or not command.strip():
            return 0
        policy = _load_policy()
        decision, rule, message = check(command, policy)
        if decision != "allow" or policy.get("log_all"):
            _log({"decision": decision, "rule": rule, "command": command[:1000],
                  "cwd": payload.get("cwd"), "session_id": payload.get("session_id"),
                  "parser": "bashlex" if _HAVE_BASHLEX else f"regex-fallback ({_BASHLEX_ERR})"})
        if decision == "block":
            print(json.dumps({"action": "block",
                              "message": f"bash_guard [{rule}]: {message}. "
                                         f"Command: {command[:300]}"}))
            return 0
        return 0
    except Exception as exc:  # fail open, but leave a trace
        _log({"decision": "error", "rule": "internal", "detail": f"{type(exc).__name__}: {exc}"})
        return 0


if __name__ == "__main__":
    sys.exit(main())
