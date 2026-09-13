#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
agent_wallet_guard.py — watchdog for LLM API spend.

Silent when healthy (empty stdout => scheduler sends nothing => zero cost).
Alerts only on anomaly, throttled:

  1) balance below floor                       (throttle: once per 12 h)
  2) actual burn this UTC day over threshold   (throttle: once per 4 h),
     with the top session by cache-read tokens as the culprit candidate
     (requires WALLET_USAGE_DB).

Design lessons baked in (from production):
  * Anchor on the REAL balance from the provider API, not on a price map.
    Price maps drifted ~2x on output tokens in our setup; cache-hit input is
    ~50-100x cheaper than fresh input and dominates agent workloads, so naive
    token*token-price math misattributes everything.
  * A single huge session (hundreds of K tokens of context replayed every
    turn, plus compression attempts that hang and retry for 6-24 minutes,
    each retry a paid aux call) is the usual budget killer. Surface its id so
    an operator can reset it.
  * A failed network fetch is NOT an alert — stay quiet and keep watching.

Environment / config:
  WALLET_BALANCE_URL    balance endpoint. Default expected shape (DeepSeek):
                        {"balance_infos":[{"currency":"USD","total_balance":12.34}]}
                        If the response is a bare number, it is used directly.
  WALLET_API_KEY        the API key. Alternative: WALLET_API_KEY_ENV=<VARNAME>
                        to read the key from another environment variable.
  WALLET_LOW_BALANCE    USD floor below which to nag (default 2.0)
  WALLET_DAILY_BURN     USD burn per UTC day that triggers (default 1.5)
  WALLET_STATE_FILE     state path (default ~/.cache/agent_wallet_guard.json)
  WALLET_USAGE_DB       optional sqlite path with table session_model_usage
                        (session_id, billing_provider, first_seen, cache_read_tokens,
                         input_tokens, output_tokens, reasoning_tokens, api_call_count)
                        -> enables the "culprit session" line.
  WALLET_PROVIDER       billing_provider value to filter in the usage query
                        (default "deepseek")

Run it every 30 min from cron. Empty stdout = OK.
"""
import json
import os
import sqlite3
import time
import urllib.request

BALANCE_URL = os.environ.get("WALLET_BALANCE_URL", "https://api.deepseek.com/user/balance")
LOW_BALANCE = float(os.environ.get("WALLET_LOW_BALANCE", "2.0"))
DAILY_BURN_ALERT = float(os.environ.get("WALLET_DAILY_BURN", "1.5"))
STATE_FILE = os.environ.get("WALLET_STATE_FILE", os.path.expanduser("~/.cache/agent_wallet_guard.json"))
USAGE_DB = os.environ.get("WALLET_USAGE_DB") or None
PROVIDER = os.environ.get("WALLET_PROVIDER", "deepseek")
SESS_CACHE_SUSPECT = 40e6  # cache tokens/day above which a session is a monster candidate


def load_key() -> str | None:
    direct = os.environ.get("WALLET_API_KEY")
    if direct:
        return direct.strip()
    varname = os.environ.get("WALLET_API_KEY_ENV")
    if varname:
        return os.environ.get(varname, "").strip() or None
    return None


def fetch_balance(key: str) -> float | None:
    req = urllib.request.Request(BALANCE_URL, headers={"Authorization": "Bearer " + key})
    with urllib.request.urlopen(req, timeout=15) as r:
        data = json.loads(r.read().decode())
    if isinstance(data, (int, float)):
        return float(data)
    for bi in data.get("balance_infos", []):
        if bi.get("currency") == "USD":
            return float(bi.get("total_balance", 0.0))
    return None


def top_session_today() -> dict | None:
    """Session with the most cache-read tokens today (the cost driver)."""
    if not USAGE_DB:
        return None
    now = time.time()
    day_start = now - (now % 86400)
    con = sqlite3.connect(f"file:{USAGE_DB}?mode=ro", uri=True, timeout=10)
    try:
        cur = con.cursor()
        cur.execute(
            """SELECT session_id,
                      COALESCE(SUM(cache_read_tokens),0),
                      COALESCE(SUM(input_tokens),0),
                      COALESCE(SUM(output_tokens),0)+COALESCE(SUM(reasoning_tokens),0),
                      COALESCE(SUM(api_call_count),0)
               FROM session_model_usage
               WHERE billing_provider=? AND first_seen >= ?
               GROUP BY session_id ORDER BY 2 DESC LIMIT 1""",
            (PROVIDER, day_start),
        )
        row = cur.fetchone()
    finally:
        con.close()
    if not row:
        return None
    return {"session_id": row[0], "cache": row[1], "in": row[2], "out": row[3], "calls": row[4]}


def load_state() -> dict:
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(st: dict) -> None:
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(st, f)


def main() -> None:
    key = load_key()
    if not key:
        print("agent-wallet-guard: no API key (set WALLET_API_KEY or WALLET_API_KEY_ENV)")
        return
    try:
        balance = fetch_balance(key)
    except Exception:
        return  # network/provider down — not an alert, keep watching
    if balance is None:
        return

    st = load_state()
    now = time.time()
    today = time.strftime("%Y-%m-%d")
    msgs: list[str] = []

    # Day rollover: the day anchor is the FIRST measurement of the new day.
    if st.get("day") != today:
        st["day"] = today
        st["day_balance0"] = balance
        st["day_alert_ts"] = 0.0

    # Top-up detected: re-anchor, so a refill is not counted as burn.
    day0 = st.get("day_balance0", balance)
    if balance > day0:
        st["day_balance0"] = balance
        day0 = balance

    burn_today = max(0.0, day0 - balance)

    # 1. Low balance — once per 12 h.
    if balance < LOW_BALANCE and now - st.get("low_alert_ts", 0.0) > 12 * 3600:
        msgs.append(f"balance {balance:.2f} USD is below {LOW_BALANCE:.2f} — time to top up.")
        st["low_alert_ts"] = now

    # 2. Actual burn for the day — once per 4 h, with the culprit session.
    if burn_today >= DAILY_BURN_ALERT and now - st.get("day_alert_ts", 0.0) > 4 * 3600:
        extra = ""
        sess = top_session_today()
        if sess and sess["cache"] > SESS_CACHE_SUSPECT:
            extra = (f"\nCulprit candidate: {sess['session_id'][:20]}… "
                     f"(cache {sess['cache']/1e6:.0f}M, {sess['calls']} calls) "
                     f"— context grew too large, reset that session.")
        msgs.append(f"burn today already -{burn_today:.2f} USD (balance {balance:.2f}).{extra}")
        st["day_alert_ts"] = now

    st["last_balance"] = balance
    st["last_ts"] = now
    save_state(st)

    if msgs:
        print("\n".join(msgs))


if __name__ == "__main__":
    main()
