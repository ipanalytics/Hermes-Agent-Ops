#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fresh_prompt_linter.py — will this cron prompt survive a fresh session?

A scheduler job runs in a BRAND-NEW session with zero chat context. The prompt
must be fully self-contained, yet humans (and LLMs) write prompts that assume
history: "as I said earlier", "the file we discussed", "you know my
preferences". The job then hallucinates, stalls, or asks the user mid-flight —
in a context where nobody answers.

This linter is a deterministic heuristic checker for that class of bug. It is
NOT a guarantee (a prompt can pass and still fail, or fail and still work) —
treat it as the code-review bot for prompt hygiene.

Usage:
  python3 fresh_prompt_linter.py --prompt-file my_job_prompt.md
  echo $?  # 0 = OK (warnings only), 1 = FAIL (block the deploy)

Design notes:
  * Deictic phrases ("as mentioned", "see above") are the #1 real failure we
    saw in production cron jobs.
  * Relative time words ("today", "yesterday", "tomorrow") are only safe when
    the prompt also contains an explicit date anchor — otherwise the job's
    "today" is whatever day it happens to run.
  * Interactive verbs ("ask me", "I'll wait") stall a headless run forever.
  * Unresolved placeholders (<thing>, {{x}}, ${x}) mean someone forgot to
    template the prompt before shipping.
"""
import argparse
import re
import sys

ANAPHORA = [
    r"as (?:i|we|you) (?:said|mentioned|discussed|noted|wrote)",
    r"as (?:above|discussed earlier|noted earlier|mentioned earlier|we agreed)",
    r"see (?:above|earlier|my previous)",
    r"from (?:our|the) (?:previous|earlier) (?:chat|conversation|message|turn)",
    r"(?:the|that|this|my) (?:last )?(?:message|answer|reply|output) (?:above|earlier|before)",
    r"the (?:user'?s|my) (?:last|previous) message",
    r"as you (?:know|remember)",
    r"in our (?:last|earlier)",
    r"the file (?:we|you|i) (?:discussed|mentioned|talked about)",
    r"you (?:said|told me|mentioned) earlier",
]

RELATIVE_TIME = [r"\btoday\b", r"\byesterday\b", r"\btomorrow\b", r"\blast night\b",
                 r"\bthis (?:week|month)\b", r"\bnext (?:week|month)\b", r"\bnow\b",
                 r"\brecently\b"]
DATE_ANCHOR = [r"\d{4}-\d{2}-\d{2}", r"\d{2}\.\d{2}\.\d{4}", r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2}"]

INTERACTIVE = [r"\bask (?:me|the user)\b", r"\bwait(?:ing)? for (?:your|the user)",
               r"\bI'?ll (?:wait|check back)", r"\bplease confirm\b", r"\bhold on\b",
               r"\bwould you like\b", r"\bshall I\b", r"\bdo you want me to\b"]

PLACEHOLDERS = [r"\{\{[^}]+\}\}", r"\$\{[^}]+\}", r"<[A-Za-z_][A-Za-z0-9_]*>"]

DELIVERY_HINT = [r"\boutput\b", r"\bformat\b", r"\breport\b", r"\breply\b",
                 r"\bdeliver\b", r"\bprint\b", r"\bsend\b", r"\bjson\b", r"\bmd\b"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt-file", required=True)
    ap.add_argument("--allow", nargs="*", default=[], help="substrings to ignore (e.g. a quoted example sentence)")
    args = ap.parse_args()

    with open(args.prompt_file, encoding="utf-8") as f:
        text = f.read()
    lower = text.lower()
    findings: list[tuple[str, str]] = []  # (level, message)

    # 1. Anaphora / history references
    for pat in ANAPHORA:
        for m in re.finditer(pat, lower):
            snippet = text[max(0, m.start() - 30):m.end() + 30].replace("\n", " ")
            if not any(a.lower() in snippet for a in args.allow):
                findings.append(("FAIL", f"references earlier context: ...{snippet}..."))
                break

    # 2. Relative time without a date anchor
    has_date = any(re.search(p, lower) for p in DATE_ANCHOR)
    if not has_date:
        for pat in RELATIVE_TIME:
            if re.search(pat, lower):
                findings.append(("WARN", "relative time word used but no explicit date anchor found — the job's 'today' drifts"))
                break

    # 3. Interactive verbs — a headless run stalls
    for pat in INTERACTIVE:
        if re.search(pat, lower):
            findings.append(("WARN", "interactive wording ('ask me' / 'wait' / 'confirm') — a scheduled job has nobody to answer"))

    # 4. Unresolved placeholders
    for pat in PLACEHOLDERS:
        for m in re.finditer(pat, text):
            snippet = text[max(0, m.start() - 20):m.end() + 20].replace("\n", " ")
            if not any(a.lower() in snippet for a in args.allow):
                findings.append(("FAIL", f"unresolved placeholder: {m.group(0)} in ...{snippet}..."))

    # 5. Delivery/output instructions present?
    if not any(re.search(p, lower) for p in DELIVERY_HINT):
        findings.append(("WARN", "no output/delivery wording found — the job does not say how to report"))

    # 6. Self-containment smell: length floor (a 1-line prompt rarely carries enough)
    if len(text.strip()) < 200:
        findings.append(("WARN", "very short prompt (<200 chars) — usually lacks rules for a fresh session"))

    fails = [f for f in findings if f[0] == "FAIL"]
    warns = [f for f in findings if f[0] == "WARN"]
    print(f"fresh-prompt-linter: {len(fails)} fail(s), {len(warns)} warning(s)")
    for level, msg in findings:
        print(f"  [{level}] {msg}")

    if fails:
        print("VERDICT: FAIL — do not ship this prompt to a scheduled job. Make it self-contained, then re-run.")
        sys.exit(1)
    print("VERDICT: OK (warnings are suggestions — read them before shipping)")
    sys.exit(0)


if __name__ == "__main__":
    main()
