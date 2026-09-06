#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cost_dashboard.py — turn the agent usage DB into a self-contained HTML panel.

The CLI guard (`01-agent-wallet-guard/agent_wallet_guard.py`) alerts when
money burns; this shows WHERE it went: spend shape by day, and the top
sessions by cache-read tokens (the real cost driver in agent workloads —
cache hits dominate, output tokens are the honest bill, aux calls add up).

Reads the same sqlite usage table as the guard:
  session_model_usage(session_id, billing_provider, first_seen,
                      cache_read_tokens, input_tokens, output_tokens,
                      reasoning_tokens, api_call_count)
Optionally a price table to convert tokens to USD (approximate, honest):
  prices: {provider: {cache_in_per_1M, in_per_1M, out_per_1M, aux_calls_per}}

Usage:
  python3 cost_dashboard.py --db usage.db --days 14 --out cost-dashboard.html
  # open the HTML in any browser; no server, no JS frameworks, one file.
"""
import argparse
import html
import json
import os
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta

# Rough public list prices (USD per 1M tokens). Provide your own via --prices.
DEFAULT_PRICES = {
    "primary":   {"cache_in": 0.07, "in": 0.55, "out": 2.19},
    "secondary": {"cache_in": 0.014, "in": 0.14, "out": 0.28},
    "aux":       {"cache_in": 0.0, "in": 0.05, "out": 0.10},
}


def usd(prov: str, row: tuple, prices: dict) -> float:
    p = prices.get(prov, prices["secondary"])
    cache, tin, tout, reas, calls = row[2], row[3], row[4], row[5], row[6]
    out = tout + reas
    return (cache * p["cache_in"] + tin * p["in"] + out * p["out"]) / 1e6 + calls * p.get("per_call", 0.0)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--out", default="cost-dashboard.html")
    ap.add_argument("--prices", default=None, help="JSON file overriding DEFAULT_PRICES")
    args = ap.parse_args()

    prices = DEFAULT_PRICES
    if args.prices:
        with open(args.prices) as f:
            prices.update(json.load(f))

    since = datetime.now() - timedelta(days=args.days)
    con = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True, timeout=15)
    try:
        cur = con.cursor()
        cur.execute(
            """SELECT session_id, billing_provider,
                      COALESCE(SUM(cache_read_tokens),0),
                      COALESCE(SUM(input_tokens),0),
                      COALESCE(SUM(output_tokens),0),
                      COALESCE(SUM(reasoning_tokens),0),
                      COALESCE(SUM(api_call_count),0)
               FROM session_model_usage
               WHERE first_seen >= ?
               GROUP BY session_id""",
            (since.timestamp(),),
        )
        rows = cur.fetchall()
    finally:
        con.close()

    per_prov: dict[str, float] = defaultdict(float)
    per_session: list[tuple[float, tuple]] = []
    for r in rows:
        cost = usd(r[1], r, prices)
        per_session.append((cost, r))
        per_prov[r[1]] += cost

    # Day granularity needs first_seen per day — second, lighter query.
    con = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True, timeout=15)
    try:
        cur = con.cursor()
        cur.execute(
            """SELECT date(first_seen, 'unixepoch') AS d,
                      billing_provider,
                      COALESCE(SUM(cache_read_tokens),0),
                      COALESCE(SUM(input_tokens),0),
                      COALESCE(SUM(output_tokens)+SUM(reasoning_tokens),0),
                      COALESCE(SUM(api_call_count),0)
               FROM session_model_usage
               WHERE first_seen >= ?
               GROUP BY d, billing_provider""",
            (since.timestamp(),),
        )
        day_rows = cur.fetchall()
    finally:
        con.close()
    per_day = defaultdict(float)
    for d, prov, cache, tin, out, calls in day_rows:
        per_day[d] += (cache * prices.get(prov, prices["secondary"])["cache_in"]
                       + tin * prices.get(prov, prices["secondary"])["in"]
                       + out * prices.get(prov, prices["secondary"])["out"]) / 1e6 \
                      + calls * prices.get(prov, prices["secondary"]).get("per_call", 0.0)

    per_session.sort(reverse=True)
    total = sum(c for c, _ in per_session)
    days_sorted = sorted(per_day.items())

    # ---- render -----------------------------------------------------------
    bars = []
    max_day = max((v for _, v in days_sorted), default=1.0) or 1.0
    for d, v in days_sorted:
        w = int(100 * v / max_day)
        bars.append(f'<div class="day"><span class="dl">{d}</span>'
                    f'<div class="bar" style="width:{w}%"></div>'
                    f'<span class="dv">${v:.2f}</span></div>')
    sess_rows = "".join(
        f'<tr><td>{html.escape(c[1][0][:24])}…</td><td>{c[1][1]}</td>'
        f'<td>{c[1][6]}</td><td>{c[1][2]/1e6:.1f}M</td><td>${c[0]:.2f}</td></tr>'
        for c in per_session[:10])
    prov_rows = "".join(f"<tr><td>{html.escape(p)}</td><td>${v:.2f}</td></tr>"
                        for p, v in sorted(per_prov.items(), key=lambda x: -x[1]))

    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Agent cost dashboard (last {args.days} days)</title>
<style>
 body{{font:14px/1.5 system-ui,sans-serif;max-width:900px;margin:2rem auto;padding:0 1rem;color:#222}}
 h1{{font-size:1.4rem}} .grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:1rem;margin:1rem 0}}
 .card{{border:1px solid #ddd;border-radius:10px;padding:1rem}}
 .big{{font-size:2rem;font-weight:700}} .muted{{color:#888}}
 .day{{display:flex;align-items:center;gap:.5rem;margin:.2rem 0}}
 .bar{{height:14px;background:#4a90d9;border-radius:4px;min-width:2px}}
 .dl{{width:90px;flex:none;color:#666;font-size:12px}} .dv{{width:56px;text-align:right;flex:none}}
 table{{border-collapse:collapse;width:100%}} td,th{{border-bottom:1px solid #eee;padding:.35rem .5rem;text-align:left}}
 th{{color:#888;font-weight:600;font-size:12px}}
</style></head><body>
<h1>Agent cost dashboard</h1>
<div class="grid">
 <div class="card"><div class="muted">total (est., last {args.days}d)</div><div class="big">${total:.2f}</div></div>
 <div class="card"><div class="muted">sessions with usage</div><div class="big">{len(rows)}</div></div>
 <div class="card"><div class="muted">busiest day</div><div class="big">{days_sorted[-1][0] if days_sorted else '—'}<span class="muted"> ${days_sorted[-1][1]:.2f if days_sorted else 0}</span></div></div>
</div>
<h3>Spend by day (est.)</h3>{''.join(bars)}
<h3>Top sessions by estimated cost</h3>
<table><tr><th>session</th><th>provider</th><th>calls</th><th>cache tokens</th><th>est.</th></tr>{sess_rows}</table>
<h3>By provider</h3><table><tr><th>provider</th><th>est.</th></tr>{prov_rows}</table>
<p class="muted">Estimates from list prices (override via --prices); the balance guard
(01) measures the FACT from the provider API — this panel is for attribution, not billing.</p>
</body></html>"""
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(page)
    print(f"wrote {os.path.abspath(args.out)} — est. total ${total:.2f} over {args.days}d")


if __name__ == "__main__":
    main()
