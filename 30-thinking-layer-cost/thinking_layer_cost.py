#!/usr/bin/env python3
"""Daily report on the "thinking layer" and spending cap.

no_agent-cron: stdout is delivered as a message, empty stdout = silence.
Counts spending from state.db (session_model_usage), balances from live requests.
"""
import json
import os
import sqlite3
import urllib.request
from datetime import datetime, timezone, timedelta


HOME = os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))
DB = os.path.join(HOME, "state.db")
ENV = os.path.join(HOME, ".env")

# Models in the "thinking layer": MoA aggregator (jobs/sessions marked with preset name),
# goal_judge and profile think
THINKING = {"minimax/minimax-m3", "brain"}
DAY_CAP_USD = 1.50          # threshold "expensive" for entire ecosystem per day
THINK_CAP_USD = 0.40        # threshold for the thinking layer itself


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
        runway = f" → at average pace ~{int(or_left / avg)} days"

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
        f"Rates: M3 $0.30/$1.20 · advisor models GLM-flash $0.15/$0.50 + DS-0731 $0.065/$0.18",
        "Layer: goal_judge + MoA aggregator + profile think → M3 (+advisors)",
        f"Daily ceiling for spending: ${DAY_CAP_USD:.2f} (thinking layer ${THINK_CAP_USD:.2f})",
        "Balance: " + (", ".join(bal) if bal else "n/a") + runway,
        f"Status: {status}",
    ]
    print("\n".join(lines))


if __name__ == "__main__":
    main()