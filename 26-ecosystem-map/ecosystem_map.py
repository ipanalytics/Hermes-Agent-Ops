#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ecosystem_map.py — live map of agent ecosystem (jobs, profiles, connections).

no_agent-cron, Monday 05:30 UTC:
1) Always rebuilds ~/.hermes/data/ecosystem_map.md from ~/.hermes/cron/jobs.json + profiles.
2) Print to stdout ONLY the diff of changes compared to the previous run (state file) —
   no changes = empty stdout = silence (watchdog pattern).
"""
import json
import os
import re
import sys
from datetime import datetime, timezone

H = os.path.expanduser
JOBS = H("~/.hermes/cron/jobs.json")
CHANNELS = H("~/.hermes/channel_directory.json")
MAP = H("~/.hermes/data/ecosystem_map.md")
STATE = H("~/.hermes/data/ecosystem_map_state.json")
PROFILES_DIR = H("~/.hermes/profiles")

# Friendly names for the topics of one group chat. Topic number -> name.
TOPIC_NAMES = {
    "16": "Media", "17": "Travel", "18": "Health", "19": "Other",
    "20": "Wearables", "30": "System", "35": "Kitchen", "82": "HQ",
    "105": "Models", "239": "Genetics", "713": "Authorities",
    "762": "Security", "763": "News", "1078": "Mail",
}
GROUP_CHAT = os.environ.get("HERMES_GROUP_CHAT", "")       # group with topics
SECOND_CHAT = os.environ.get("HERMES_SECOND_CHAT", "")     # a second group, if any


def deliver_label(job):
    """deliver -> human-readable delivery target."""
    d = job.get("deliver") or "origin"
    if d == "local":
        return "local"
    if d == "origin":
        o = job.get("origin") or {}
        if o.get("chat_id") == os.environ.get("HERMES_OPERATOR_CHAT", ""):
            return "📩 direct"
        thr = o.get("thread_id")
        chat = o.get("chat_id", "?")
        if chat == GROUP_CHAT:
            return f"t.{thr} '{TOPIC_NAMES.get(str(thr), '?')}'" if thr else "group with topics"
        if chat == SECOND_CHAT:
            return "second group"
        return f"chat {chat}"
    m = re.match(r"^(?:telegram:)?([^:]+)(?::(\d+))?$", d)
    if not m:
        return d
    chat, thr = m.group(1), m.group(2)
    if chat == os.environ.get("HERMES_OPERATOR_CHAT", ""):
        return "📩 direct"
    if chat == GROUP_CHAT:
        return f"t.{thr} '{TOPIC_NAMES.get(thr, '?')}'" if thr else "group with topics"
    if chat == SECOND_CHAT:
        return "second group"
    return f"chat {chat}" + (f":{thr}" if thr else "")


def fmt_last(job):
    lr = job.get("last_run_at")
    date = lr[:10] if lr else "never"
    status = job.get("last_status")
    streak = job.get("failure_streak") or 0
    if status == "error" or streak > 0:
        return f"🔴 {status} ×{streak} ({date})"
    if status == "ok":
        return f"🟢 {date}"
    return f"⚪ {status or 'not run'}"


def build_map(jobs, profiles, channels_idx):
    lines = []
    active = [j for j in jobs if j.get("state") == "scheduled"]
    paused = [j for j in jobs if j.get("state") == "paused"]
    done = [j for j in jobs if j.get("state") == "completed"]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines.append("# Agent Ecosystem Map")
    lines.append(f"*generated {now} · source jobs.json (updated "
                 f"{jobs[0].get('_updated', '?')})*")
    lines.append("")
    lines.append(f"**Crons:** total {len(jobs)} · active {len(active)} · "
                 f"paused {len(paused)} · completed one-offs {len(done)}")
    lines.append("")
    lines.append("## Profiles")
    for p in profiles:
        tag = " (main)" if p == "default" else ""
        lines.append(f"- {p}{tag}")
    lines.append("")

    probs = [j for j in jobs if (j.get("last_status") == "error" or (j.get("failure_streak") or 0) > 0)
             and j.get("state") != "completed"]
    if probs:
        lines.append("## ⚠️ Problems")
        for j in probs:
            lines.append(f"- {j['name']} ({j['id'][:8]}) — {fmt_last(j)}")
        lines.append("")

    # Group by delivery targets (active + paused only).
    by_target = {}
    for j in active + paused:
        by_target.setdefault(deliver_label(j), []).append(j)
    lines.append("## Crons by delivery targets")
    for target in sorted(by_target):
        lines.append(f"### {target}")
        for j in sorted(by_target[target], key=lambda x: x["name"].lower()):
            sched = j.get("schedule_display") or ""
            if j.get("no_agent"):
                kind = f"⚙️ {j.get('script')}"
            else:
                model = j.get("model") or "?"
                kind = f"🤖 {model.split('/')[-1]}"
            state_mark = "⏸ " if j.get("state") == "paused" else ""
            lines.append(f"- {state_mark}{j['name']} · `{j['id'][:8]}` · {sched} · "
                         f"{kind} · {fmt_last(j)}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def diff_report(old_state, jobs):
    """Compare to previous run -> change lines (or empty)."""
    old = (old_state or {}).get("jobs", {})
    cur = {j["id"]: j for j in jobs}
    out = []
    # Added / removed (without completed one-offs).
    for jid, j in cur.items():
        if jid not in old and j.get("state") in ("scheduled", "paused"):
            out.append(f"➕ new cron: {j['name']} ({j.get('schedule_display')})")
    for jid, o in old.items():
        if jid not in cur and o.get("state") in ("scheduled", "paused"):
            out.append(f"➖ removed cron: {o.get('name')}")
    # State transitions.
    for jid, j in cur.items():
        o = old.get(jid)
        if not o:
            continue
        ns, os_ = j.get("state"), o.get("state")
        if ns != os_ and os_ in ("scheduled", "paused") and ns in ("scheduled", "paused"):
            word = "resumed ▶️" if ns == "scheduled" else "paused ⏸"
            out.append(f"{word}: {j['name']}")
    # Errors now.
    for jid, j in cur.items():
        if j.get("state") == "completed":
            continue
        err = j.get("last_status") == "error" or (j.get("failure_streak") or 0) > 0
        old_err = (old.get(jid) or {}).get("_err")
        if err and not old_err:
            out.append(f"⚠️ {j['name']}: {fmt_last(j)}")
    return out


def main():
    with open(JOBS) as f:
        data = json.load(f)
    jobs = data["jobs"]
    for j in jobs:
        j["_updated"] = data.get("updated_at", "?")
    try:
        with open(CHANNELS) as f:
            ch = json.load(f)
    except Exception:
        ch = {}
    channels_idx = {}
    for p in ch.get("platforms", {}).get("telegram", []):
        key = p["id"]
        channels_idx[key] = p.get("name", "")
        if p.get("thread_id") and key.count(":") == 1:
            pass
    profiles = []
    if os.path.isdir(PROFILES_DIR):
        profiles = sorted(d for d in os.listdir(PROFILES_DIR)
                          if os.path.isdir(os.path.join(PROFILES_DIR, d)))
    profiles = ["default"] + [p for p in profiles if p != "default"]

    old_state = None
    if os.path.exists(STATE):
        try:
            with open(STATE) as f:
                old_state = json.load(f)
        except Exception:
            old_state = None

    new_state = {"generated": datetime.now(timezone.utc).isoformat(),
                 "jobs": {j["id"]: {"name": j.get("name"), "state": j.get("state"),
                                     "_err": (j.get("last_status") == "error" or
                                              (j.get("failure_streak") or 0) > 0)}
                          for j in jobs}}
    tmp = MAP + ".tmp"
    with open(tmp, "w") as f:
        f.write(build_map(jobs, profiles, channels_idx))
    os.replace(tmp, MAP)
    with open(STATE + ".tmp", "w") as f:
        json.dump(new_state, f, ensure_ascii=False, indent=1)
    os.replace(STATE + ".tmp", STATE)

    changes = diff_report(old_state, jobs)
    if changes:
        print("📊 **Ecosystem map** — changes this week:")
        for c in changes:
            print(f"• {c}")
        print(f"Full map: `~/.hermes/data/ecosystem_map.md`")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"⚠️ ecosystem_map.py: {e}")
        sys.exit(1)