#!/usr/bin/env python3
"""skill_scan — vet a skill / prompt file / agent config before it is trusted.

Why: a skill is executable policy written by a stranger. It can carry prompt injection,
secret exfiltration, remote-code-execution one-liners, or hidden (zero-width / bidi)
instructions that never render in a diff. This scanner scores those patterns and can be
wired as a `pre_tool_call` shell hook so an install is blocked instead of trusted.

Usage:
  skill_scan.py PATH [PATH ...]        # human report (dir walks **/SKILL.md and *.md)
  skill_scan.py PATH --json            # machine report
  skill_scan.py --hook                 # pre_tool_call shell-hook mode (stdin JSON)
  skill_scan.py --all-installed        # scan ~/.hermes/skills (baseline audit)

Exit codes: 0 = clean/info, 2 = HIGH finding(s), 1 = usage error.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys

HOME = os.environ.get("HERMES_HOME") or os.path.join(os.path.expanduser("~"), ".hermes")

# (id, severity, regex, note)
RULES = [
    # ── HIGH: stealth / injection ───────────────────────────────────────────
    ("injection-override", "HIGH",
     r"(?i)\b(ignore|disregard|forget)\b[^.\n]{0,30}\b(previous|prior|above|earlier)\b"
     r"[^.\n]{0,30}\b(instruction|prompt|rules?|context)\b",
     "tells the agent to drop its earlier instructions"),
    ("injection-role", "HIGH",
     r"(?i)\byou are now\b|\bact as (?:the|a) (?:system|developer)\b|\bnew system prompt\b",
     "attempts to reassign the agent's role"),
    ("stealth-user", "HIGH",
     # "do not tell the user ABOUT/THAT/THIS" = hiding; "never tell a user TO put X in .env"
     # is an instruction to the reader and must NOT match.
     r"(?i)\b(?:do not|don't|never)\b[^.\n]{0,20}\b(?:tell|inform|notify|reveal|mention)\b"
     r"[^.\n]{0,15}\b(?:the|any|a) user\b(?!\s+to\b)"
     r"|\bбез ведома\b|\bне (?:говори|сообщай|упоминай)\b[^.\n]{0,20}\bпользовател\w*",
     "asks to hide actions from the user"),
    ("hidden-unicode", "HIGH",
     r"[\u200b\u200c\u200d\u2060\u202a-\u202e\u2066-\u2069]{3,}",
     "invisible / bidi control characters (text that does not render)"),
    # ── HIGH: secrets ────────────────────────────────────────────────────────
    ("secret-path", "HIGH",
     r"(?:\.hermes/\.env|\.hermes/auth\.json|\.ssh/id_[a-z0-9]+|\.aws/credentials|"
     r"/etc/shadow|\.netrc|shell-hooks-allowlist\.json)",
     "reads a credential store"),
    ("exfil-network", "HIGH",
     r"(?i)(webhook\.site|pipedream\.net|requestbin|pastebin\.com|0x0\.st|ngrok\.io|"
     r"transfer\.sh|discord(?:app)?\.com/api/webhooks|api\.telegram\.org/bot[^/]*/sendMessage)",
     "public drop-box / webhook used for exfiltration"),
    ("exfil-combo", "HIGH",
     r"(?is)(?:curl|wget|nc|ncat|socat)\b[^\n]{0,120}?(?:\$\(|`)[^\n]{0,60}"
     r"(?:cat|base64)\b[^\n]{0,120}?(?:\.env|auth\.json|id_rsa|\.ssh)",
     "command substitution feeding a secret into a network call"),
    # ── HIGH: remote code execution ─────────────────────────────────────────
    ("pipe-to-shell", "HIGH",
     r"(?i)(?:curl|wget)\b[^|\n]{0,200}\|\s*(?:sudo\s+)?(?:ba|z|da)?sh\b",
     "downloads and executes a remote script"),
    ("decode-pipe-shell", "HIGH",
     r"(?i)(?:base64\s+(?:-d|--decode)|xxd\s+-r|openssl\s+enc\s+-d)\b[^|\n]{0,80}\|\s*"
     r"(?:sudo\s+)?(?:ba|z|da)?sh\b",
     "decodes a payload straight into a shell"),
    ("eval-fetch", "HIGH",
     r"(?i)\beval\b[^\n]{0,40}\$\((?:curl|wget)\b",
     "eval of a fetched string"),
    # ── HIGH: destruction ───────────────────────────────────────────────────
    ("destroy-root", "HIGH",
     r"(?i)\brm\s+-[a-z]*[rf][a-z]*\s+(?:--no-preserve-root\s+)?/(?:\s|$|\*)"
     r"|\bmkfs(?:\.\w+)?\b|\bdd\b[^\n]{0,40}of=/dev/(?:sd|nvme|hd)",
     "destroys the filesystem / a block device"),
    ("disable-safety", "HIGH",
     r"(?i)\b(?:setenforce\s+0|systemctl\s+(?:stop|disable)\s+(?:firewalld|ufw|apparmor)|"
     r"iptables\s+-F|ufw\s+disable)\b",
     "turns off a security control"),
    # ── MEDIUM ──────────────────────────────────────────────────────────────
    ("long-base64", "MEDIUM", r"[A-Za-z0-9+/]{200,}={0,2}",
     "long encoded blob (payload or embedded binary)"),
    ("raw-ip-url", "MEDIUM", r"https?://\d{1,3}(?:\.\d{1,3}){3}(?::\d+)?",
     "bare-IP URL (no TLS hostname to audit)"),
    ("persistence-cron", "MEDIUM",
     r"(?i)\bcrontab\s+-|/etc/cron\.\w+/|systemctl\s+enable\s+\S+\.(?:service|timer)|"
     r">>\s*~?/?\.(?:bashrc|profile|zshrc)\b",
     "installs persistence"),
    ("sudo-use", "MEDIUM", r"(?i)\bsudo\s+(?:-S|tee|cp|mv|chmod|chown|rm)\b",
     "privileged file operation"),
    ("outbound-post", "MEDIUM",
     r"(?i)\bcurl\b[^\n]{0,80}\b(?:-d|--data|-F|--form|-T|--upload-file)\b",
     "posts/uploads data to a remote endpoint"),
    ("browser-cookie", "MEDIUM",
     r"(?i)Cookies|cookies\.sqlite|Login Data|keychain|security find-generic-password",
     "touches browser/OS credential material"),
    # ── LOW / INFO ──────────────────────────────────────────────────────────
    ("network-call", "LOW", r"(?i)\b(?:curl|wget|httpie|httpx)\b", "makes network calls"),
    ("env-write", "LOW", r"(?i)\b(?:>>?|tee)\s*\S*\.env\b", "writes an .env file"),
]

SEV_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}

# Documented, widely used installers: a `curl | bash` on these is normal onboarding text,
# not evidence of malice. Kept at MEDIUM so it still shows up in a review.
TRUSTED_INSTALLERS = (
    "hermes-agent.nousresearch.com", "nousresearch.com", "astral.sh", "sh.rustup.rs",
    "get.docker.com", "brew.sh", "tailscale.com", "raw.githubusercontent.com",
    "claude.ai", "code.visualstudio.com", "get.pnpm.io", "bun.sh", "deno.land",
)

# Rules that mean "credentials are touched"; escalated to HIGH only when the same file
# also has a way to move them out. Alone they are MEDIUM — every SSH/API doc mentions them.
SECRET_RULES = {"secret-path"}
EGRESS_RULES = {"exfil-network", "exfil-combo", "pipe-to-shell", "decode-pipe-shell",
                "outbound-post", "network-call", "raw-ip-url"}
COMBO_RULES = {"secret-path", "pipe-to-shell"}


def finalize_findings(findings: list[dict], text: str) -> list[dict]:
    """Context-aware severity: combinations are what matter, single mentions are noise."""
    present = {f["id"] for f in findings}
    out: list[dict] = []
    seen = set()
    for f in findings:
        key = (f["id"], f["line"], f["snippet"])
        if key in seen:
            continue
        seen.add(key)
        rule, sev = f["id"], f["severity"]
        if rule in SECRET_RULES:
            if present & EGRESS_RULES:
                sev, f["note"] = "HIGH", "credentials + egress path in the same file"
            else:
                sev, f["note"] = "MEDIUM", "mentions a credential store (review intent)"
        elif rule == "pipe-to-shell":
            host = ""
            m = re.search(r"https?://([^/\s]+)", f["snippet"] or "")
            if m:
                host = m.group(1).lower()
            if any(host.endswith(t) for t in TRUSTED_INSTALLERS if host):
                sev, f["note"] = "MEDIUM", f"download-and-execute from a known installer ({host})"
        elif rule == "outbound-post" and not (present & (SECRET_RULES | {"exfil-network", "exfil-combo"})):
            sev, f["note"] = "LOW", "posts/uploads data (no secret or drop-box in this file)"
        f["severity"] = sev
        out.append(f)
    out.sort(key=lambda f: (SEV_ORDER.get(f["severity"], 9), f["line"]))
    return out


def scan_text(text: str, limit: int = 3) -> list[dict]:
    findings: list[dict] = []
    lines = text.splitlines()
    for rule_id, severity, pattern, note in RULES:
        try:
            rx = re.compile(pattern, re.MULTILINE)
        except re.error:
            continue
        hits = 0
        for match in rx.finditer(text):
            if hits >= limit:
                break
            line_no = text.count("\n", 0, match.start()) + 1
            snippet = lines[line_no - 1].strip()[:180] if line_no - 1 < len(lines) else ""
            findings.append({"id": rule_id, "severity": severity, "line": line_no,
                             "snippet": snippet, "note": note})
            hits += 1
    findings.sort(key=lambda f: (SEV_ORDER.get(f["severity"], 9), f["line"]))
    return findings


def collect_paths(paths: list[str]) -> list[str]:
    files: list[str] = []
    for path in paths:
        path = os.path.expanduser(path)
        if os.path.isfile(path):
            files.append(path)
        elif os.path.isdir(path):
            for pattern in ("**/SKILL.md", "**/*.md", "**/*.sh", "**/*.py", "**/*.yaml", "**/*.yml"):
                files.extend(glob.glob(os.path.join(path, pattern), recursive=True))
    seen, out = set(), []
    for f in files:
        real = os.path.realpath(f)
        if real not in seen and os.path.isfile(f) and os.path.getsize(f) < 2_000_000:
            seen.add(real)
            out.append(f)
    return sorted(out)


def scan_files(paths: list[str]) -> dict:
    report = {"files": [], "high": 0, "medium": 0, "low": 0}
    for path in paths:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError:
            continue
        findings = finalize_findings(scan_text(text), text)
        counts = {s: sum(1 for f in findings if f["severity"] == s) for s in SEV_ORDER}
        report["high"] += counts["HIGH"]
        report["medium"] += counts["MEDIUM"]
        report["low"] += counts["LOW"]
        report["files"].append({"path": path, "findings": findings, "counts": counts})
    return report


def verdict(report: dict) -> str:
    if report["high"]:
        return "REJECT/REVIEW — high-severity findings"
    if report["medium"]:
        return "REVIEW — medium findings, check intent"
    if report["low"]:
        return "OK — only informational hits"
    return "CLEAN"


def print_human(report: dict, quiet_low: bool = True) -> None:
    for entry in report["files"]:
        findings = [f for f in entry["findings"] if not (quiet_low and f["severity"] == "LOW")]
        if not findings and report["high"] == 0 and report["medium"] == 0:
            continue
        head = entry["counts"]
        if head["HIGH"] == 0 and head["MEDIUM"] == 0:
            continue
        print(f"\n{entry['path']}  [HIGH {head['HIGH']} / MED {head['MEDIUM']} / "
              f"LOW {head['LOW']}]")
        for f in findings:
            print(f"  {f['severity']:<6} L{f['line']:<5} {f['id']:<20} {f['note']}")
            if f["snippet"]:
                print(f"          > {f['snippet']}")
    print(f"\nTOTAL: {report['high']} high, {report['medium']} medium, {report['low']} low "
          f"across {len(report['files'])} file(s)")
    print(f"VERDICT: {verdict(report)}")


def hook_mode() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    try:
        tool_input = payload.get("tool_input") or {}
        blobs = []
        for key in ("content", "file_content", "text", "body", "new_string"):
            value = tool_input.get(key)
            if isinstance(value, str) and value.strip():
                blobs.append(value)
        if not blobs:
            return 0
        findings = []
        for blob in blobs:
            findings.extend(finalize_findings(scan_text(blob, limit=2), blob))
        high = [f for f in findings if f["severity"] == "HIGH"]
        if high:
            ids = ", ".join(sorted({f"{f['id']} (L{f['line']})" for f in high}))
            print(json.dumps({
                "action": "block",
                "message": f"skill_scan: refusing to install content with HIGH-risk patterns: "
                           f"{ids}. Inspect the file, then re-run with an explicit decision."}))
        return 0
    except Exception:
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Vet skills/prompt files before trusting them")
    parser.add_argument("paths", nargs="*", help="files or directories to scan")
    parser.add_argument("--json", action="store_true", help="machine-readable report")
    parser.add_argument("--hook", action="store_true", help="pre_tool_call shell-hook mode (stdin JSON)")
    parser.add_argument("--all-installed", action="store_true",
                        help="scan every installed skill under $HERMES_HOME/skills")
    parser.add_argument("--show-low", action="store_true", help="include LOW findings in the report")
    args = parser.parse_args()

    if args.hook:
        return hook_mode()
    paths = list(args.paths)
    if args.all_installed:
        paths.append(os.path.join(HOME, "skills"))
    if not paths:
        parser.error("give a path, or --hook, or --all-installed")
    files = collect_paths(paths)
    report = scan_files(files)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print_human(report, quiet_low=not args.show_low)
    return 2 if report["high"] else 0


if __name__ == "__main__":
    sys.exit(main())
