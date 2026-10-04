#!/usr/bin/env python3
"""Daily report on the "thinking layer" plus a spending cap.

no_agent-cron: stdout is delivered as a message, empty stdout = silence.
Counts spending from state.db (session_model_usage), balances from live requests.
"""
import json
import os
import sqlite3
import urllib.request
from datetime import date, datetime, timezone, timedelta

HOME = os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))
DB = os.path.join(HOME, "state.db")
ENV = os.path.join(HOME, ".env")

# Models in the "thinking layer": MoA aggregator (jobs/sessions marked with preset name),
# goal_judge and profile think
THINKING = {"minimax/minimax-m3", "brain"}
DAY_CAP_USD = 1.50          # "expensive" threshold for the whole ecosystem per day
THINK_CAP_USD = 0.40        # threshold for the thinking layer itself

# Slot newcomers: reported daily for the first WATCH_DAYS days, then the line goes quiet
# on its own (the keep-or-drop decision is the operator's, not the script's).
WATCH_DAYS = 5
# Optional watch list for slot newcomers, kept out of the code so the script stays generic:
#   ~/.hermes/data/thinking_layer_watch.json
#   {"<model-id>": ["<YYYY-MM-DD start>", "<why this model is being watched>"]}
# The line prints for the first WATCH_DAYS days and then goes quiet on its own.
WATCH_FILE = os.path.join(HOME, "data", "thinking_layer_watch.json")


def load_watch():
    """Read the optional watch list; missing/broken file means nothing to watch."""
    try:
        with open(WATCH_FILE, encoding="utf-8") as fh:
            raw = json.load(fh)
        out = {}
        for key, value in (raw or {}).items():
            start, why = value[0], value[1]
            out[str(key)] = (str(start), str(why))
        return out
    except (OSError, ValueError, TypeError, IndexError, KeyError):
        return {}


def env(key, default=""):
    try:
        for line in open(ENV):
            line = line.strip()
            if line.startswith(key + "="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    return default


def api(url, token):
    try:
        req = urllib.request.Request(url, headers={"Authorization": "Bearer " + token})
        return json.load(urllib.request.urlopen(req, timeout=20))
    except Exception:
        return None


def cache_hit_stats(hours=24):
    """Cache hit rate and spend per model over a window (last_seen is epoch seconds). Read-only."""
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        rows = con.execute(
            "select coalesce(model,'?'), sum(coalesce(input_tokens,0)), sum(coalesce(cache_read_tokens,0)),"
            " sum(coalesce(output_tokens,0)), sum(coalesce(estimated_cost_usd,0))"
            " from session_model_usage where last_seen >= strftime('%s','now') - ? * 3600"
            " group by 1 order by 5 desc",
            (hours,),
        ).fetchall()
    finally:
        con.close()
    tin = tcr = tout = 0
    tcost = 0.0
    per = []
    for model, i, cr, o, cost in rows:
        i, cr, o, cost = i or 0, cr or 0, o or 0, cost or 0.0
        hit = 100.0 * cr / (i + cr) if (i + cr) else 0.0
        per.append((model, hit, cost))
        tin += i
        tcr += cr
        tout += o
        tcost += cost
    overall = 100.0 * tcr / (tin + tcr) if (tin + tcr) else 0.0
    return overall, tin, tcr, tout, tcost, per


def watch_report(today, watch=None):
    """One line per watched slot newcomer for the first WATCH_DAYS days, then silence."""
    watch = load_watch() if watch is None else watch
    if not watch:
        return []
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    out = []
    try:
        for model, (start, where) in watch.items():
            day = (date.fromisoformat(today) - date.fromisoformat(start)).days + 1
            if day < 1 or day > WATCH_DAYS:
                continue
            row = con.execute(
                "select sum(coalesce(api_call_count,0)), sum(coalesce(input_tokens,0)),"
                " sum(coalesce(cache_read_tokens,0)), sum(coalesce(output_tokens,0)),"
                " sum(coalesce(estimated_cost_usd,0)) from session_model_usage where model=?",
                (model,),
            ).fetchone()
            calls, i, cr, o, cost = [(x or 0) for x in (row or (0, 0, 0, 0, 0))]
            hit = 100.0 * cr / (i + cr) if (i + cr) else 0.0
            out.append(
                f"🆕 Newcomer {model.split('/')[-1]} · day {day}/{WATCH_DAYS}: {int(calls)} calls,"
                f" ${cost:.3f}, cache hit {hit:.0f}% · {where}"
            )
    finally:
        con.close()
    return out


def main():
    now = datetime.now(timezone.utc)
    today = now.date().isoformat()
    week_ago = (now - timedelta(days=7)).date().isoformat()

    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    rows = con.execute(
        "select date(first_seen,'unixepoch') d, model, "
        "sum(api_call_count), sum(estimated_cost_usd) "
        "from session_model_usage where first_seen > strftime('%s','now','-8 days') "
        "group by 1,2"
    ).fetchall()
    con.close()

    day_total, day_think, think_calls, per_day = {}, 0.0, 0, {}
    for d, model, calls, cost in rows:
        cost = cost or 0.0
        calls = calls or 0
        day_total[d] = day_total.get(d, 0.0) + cost
        if model in THINKING:
            day_think += cost if d == today else 0.0
            think_calls += calls if d == today else 0
        per_day.setdefault(d, 0.0)

    full_days = sorted(d for d in day_total if week_ago <= d < today)
    if not full_days:
        full_days = sorted(d for d in day_total if d != today)
    peak = max((day_total[d] for d in full_days), default=0.0)
    avg = (sum(day_total[d] for d in full_days) / len(full_days)) if full_days else 0.0
    peak_day = max(full_days, key=lambda d: day_total[d]) if full_days else "-"

    today_total = day_total.get(today, 0.0)

    or_left = ds_left = None
    c = api("https://openrouter.ai/api/v1/credits", env("OPENROUTER_API_KEY"))
    if c and c.get("data"):
        or_left = c["data"].get("total_credits", 0) - c["data"].get("total_usage", 0)
    b = api("https://api.deepseek.com/user/balance", env("DEEPSEEK_API_KEY"))
    if b and b.get("balance_infos"):
        ds_left = float(b["balance_infos"][0].get("total_balance") or 0)

    runway = ""
    if or_left is not None and avg > 0:
        runway = f" → ~{int(or_left / avg)} days at the recent pace"

    status = "✅"
    if today_total >= DAY_CAP_USD or day_think >= THINK_CAP_USD:
        status = "⚠️ above threshold"

    bal = []
    if or_left is not None:
        bal.append(f"OR ${or_left:.2f}")
    if ds_left is not None:
        bal.append(f"DS ${ds_left:.2f}")

    lines = [
        f"💰 Thinking layer · {today}",
        f"M3: ${day_think:.3f} ({think_calls} calls) | total per day: ${today_total:.3f}",
        f"Max/day for week: ${peak:.2f} ({peak_day}) · average ${avg:.2f}",
        f"Rates: M3 $0.30/$1.20 · advisors GLM-flash $0.15/$0.50 + DS-0731 $0.065/$0.18",
        "Layer: goal_judge + MoA aggregator + profile think → M3 (+advisors)",
        f"Daily caps: ${DAY_CAP_USD:.2f} total (thinking layer ${THINK_CAP_USD:.2f})",
        "Balance: " + (", ".join(bal) if bal else "n/a") + runway,
        f"Status: {status}",
    ]
    hit, tin, tcr, tout, tcost, per = cache_hit_stats(24)
    lines.append(
        f"🎯 Cache hit (24h): {hit:.1f}% · in {tin//1000}k / cache {tcr//1000}k / out {tout//1000}k · ${tcost:.3f}"
    )
    for _m, _h, _c in per[:3]:
        lines.append(f"   · {_m.split('/')[-1][:28]}: hit {_h:.0f}% · ${_c:.3f}")

    lines.extend(watch_report(today))

    print("\n".join(lines))


if __name__ == "__main__":
    main()
