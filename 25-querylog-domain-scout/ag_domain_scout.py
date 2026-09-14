#!/usr/bin/env python3
"""ag_domain_scout.py — which domains each device requests (AdGuard querylog).

Task: baseline known domains per client + report on 'what's new'.
Data: querylog.json accessible via SSH tunnel.
Modes:
  baseline  — load entire current querylog.json (window ~7 days) into database
  tick      — fetch only tail (default 8 MB) and update database
Report prints to stdout: new domains per client for N days (default 7).
"""
import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone

KEY = os.environ.get("SSH_KEY_PATH", "~/.ssh/id_ed25519")
REMOTE = os.environ.get("QUERYLOG_PATH", "/opt/AdGuardHome/data/data/querylog.json")
DB = os.environ.get("DATABASE_PATH", "./ag_scout.db")
BLOCKS = os.environ.get("BLOCKLIST_PATH", "./ag_blocks.json")
SSH_HOST = os.environ.get("ADGUARD_HOST", "adguard.local")
SSH_PORT = os.environ.get("SSH_PORT", "22")
SSH_USER = os.environ.get("SSH_USER", "adguard")

SSH = ["ssh", "-p", SSH_PORT, "-o", "StrictHostKeyChecking=no", "-o", "BatchMode=yes",
       "-o", "LogLevel=ERROR", "-i", os.path.expanduser(KEY), f"{SSH_USER}@{SSH_HOST}"]

# Clients (by traffic fingerprint; IPs may change)
CLIENTS = {
    # These should be customized based on your network
    # Example: "192.168.1.100": "DeviceName",
}

# Technical noise that is not interesting in reports
NOISE = re.compile(
    r"(\.arpa$|\.internal$|\.local$|^_|^[0-9a-f-]{20,}\.|"
    r"\.(clerk|sentry|segment|amplitude|mixpanel|datadog|newrelic)\.)",
    re.I,
)


def ssh_capture(args, timeout=300):
    return subprocess.run(SSH + args, capture_output=True, timeout=timeout).stdout


def pull(mode, tail_bytes=8_000_000):
    if mode == "baseline":
        cmd = ["cat", REMOTE]
    else:
        cmd = ["tail", "-c", str(tail_bytes), REMOTE]
    
    result = subprocess.run(["ssh", "-p", SSH_PORT, "-i", os.path.expanduser(KEY), 
                             f"{SSH_USER}@{SSH_HOST}"] + cmd, 
                            capture_output=True, text=True, timeout=600)
    
    if result.returncode != 0:
        raise Exception(f"SSH command failed: {result.stderr}")
    
    return result.stdout


def init_db(con):
    con.execute("""CREATE TABLE IF NOT EXISTS seen(
        client TEXT, domain TEXT, first_seen TEXT, last_seen TEXT,
        queries INTEGER DEFAULT 0, blocked INTEGER DEFAULT 0,
        PRIMARY KEY(client, domain))""")
    con.execute("""CREATE TABLE IF NOT EXISTS runs(
        ts TEXT PRIMARY KEY, mode TEXT, records INTEGER, new_domains INTEGER)""")
    con.execute("CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT)")
    con.commit()


def get_baseline(con):
    r = con.execute("SELECT value FROM meta WHERE key='baseline_ts'").fetchone()
    return r[0] if r else None


def report_cut(con, days):
    """Beginning of 'new' window: no earlier than the moment watching started (baseline)."""
    cut = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S")
    b = get_baseline(con)
    return max(cut, b) if b else cut


def parse(text):
    """-> list of (client, domain, ts_utc, blocked)"""
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        qh = (r.get("QH") or "").lower().rstrip(".")
        ip = r.get("IP") or ""
        t = r.get("T") or ""
        if not qh or not t:
            continue
        res = r.get("Result") or {}
        blocked = str(res.get("IsFiltered", "")).lower() == "true"
        out.append((ip, qh, t[:19], blocked))
    return out


def ingest(con, rows, days):
    cut = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S")
    new = 0
    for ip, qh, t, blocked in rows:
        client = CLIENTS.get(ip, f"unknown/{ip}")
        if NOISE.search(qh) or t < cut:
            continue
        cur = con.execute("SELECT first_seen, last_seen, queries, blocked FROM seen WHERE client=? AND domain=?",
                          (client, qh)).fetchone()
        if cur is None:
            con.execute("INSERT INTO seen(client, domain, first_seen, last_seen, queries, blocked) "
                        "VALUES(?,?,?,?,1,?)", (client, qh, t, t, 1 if blocked else 0))
            new += 1
        else:
            fs, ls, q, b = cur
            con.execute("UPDATE seen SET first_seen=?, last_seen=?, queries=?, blocked=? "
                        "WHERE client=? AND domain=?",
                        (min(fs, t), max(ls, t), q + 1, 1 if (b or blocked) else 0, client, qh))
    con.commit()
    return new


def block_status(con):
    """Status of recently added blocks: are they actually blocking?
    Returns list of problematic ones (requested after addition but never filtered)."""
    rows = []
    try:
        data = json.load(open(BLOCKS, encoding="utf-8"))
    except Exception:
        return rows
    for batch in data.get("batches", []):
        added = batch.get("added", "")[:19]
        for r in batch.get("rules", []):
            dom, client = r["domain"], r.get("client")
            q = con.execute(
                "SELECT count(*), sum(blocked), max(last_seen), max(first_seen) FROM seen "
                "WHERE domain=? AND (? IS NULL OR client=?)", (dom, client, client)).fetchone()
            total, blk, last, first = q[0], q[1] or 0, q[2], q[3]
            if not total or not last or last < added:
                continue  # after adding rule, domain hasn't been requested yet - nothing to judge
            if blk == 0:
                rows.append(f"{dom} ({client}) — after blocking {total} requests, NONE were filtered")
    return rows


def report(con, days=7, per_client=25):
    cut = report_cut(con, days)
    print(f"# New domains in {days} days (AdGuard, per client)")
    tot_new = 0
    for client, in con.execute("SELECT DISTINCT client FROM seen ORDER BY client"):
        rows = con.execute(
            "SELECT domain, first_seen, queries, blocked FROM seen "
            "WHERE client=? AND first_seen>=? ORDER BY queries DESC LIMIT ?",
            (client, cut, per_client)).fetchall()
        total = con.execute("SELECT count(*) FROM seen WHERE client=? AND first_seen>=?",
                            (client, cut)).fetchone()[0]
        allc = con.execute("SELECT count(*) FROM seen WHERE client=?", (client,)).fetchone()[0]
        tot_new += total
        print(f"\n## {client}: new {total} of {allc} known"
              + (f" (showing top-{per_client} by frequency)" if total > per_client else ""))
        for dom, fs, q, b in rows:
            mark = " [already blocked]" if b else ""
            print(f"  {fs[:10]}  q={q:<5} {dom}{mark}")
    print(f"\nTOTAL new: {tot_new}")
    probs = block_status(con)
    print("\n## Status of added blocks")
    if probs:
        for p in probs:
            print(f"  ⚠️ NOT BLOCKING: {p}")
    else:
        print("  all added rules either block or domain hasn't been requested")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["baseline", "tick"], default="tick")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--tail-bytes", type=int, default=8_000_000)
    ap.add_argument("--no-ingest", action="store_true", help="only show report, don't touch DB")
    ap.add_argument("--quiet", action="store_true",
                    help="quiet mode for daily cron: only summary line and new domains")
    ap.add_argument("--alerts", action="store_true",
                    help="watchdog: print ONLY problems (rule not blocking) — empty = nothing to write")
    a = ap.parse_args()

    con = sqlite3.connect(DB)
    init_db(con)
    if not a.no_ingest:
        text = pull(a.mode, a.tail_bytes)
        rows = parse(text)
        new = ingest(con, rows, a.days)
        con.execute("INSERT OR REPLACE INTO runs(ts, mode, records, new_domains) VALUES(?,?,?,?)",
                    (datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"), a.mode, len(rows), new))
        if a.mode == "baseline":
            con.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('baseline_ts', ?)",
                        (datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),))
            con.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('baseline_rows', ?)", (str(len(rows)),))
        con.commit()
        if not a.alerts:
            print(f"[collector] mode={a.mode} records={len(rows)} new pairs=({new})", file=sys.stderr)
    if a.alerts:
        probs = block_status(con)
        if probs:
            print("AdGuard: rules not blocking —")
            for p in probs:
                print("  ⚠️ " + p)
        return
    if a.quiet:
        cut = report_cut(con, a.days)
        rows = con.execute("SELECT client, count(*) FROM seen WHERE first_seen>=? GROUP BY client ORDER BY 2 DESC",
                           (cut,)).fetchall()
        if not rows:
            print("AdGuard: no new domains")
        else:
            print("AdGuard, new domains in %d d: %s" % (
                a.days, " · ".join(f"{c}={n}" for c, n in rows)))
        return
    report(con, a.days)


if __name__ == "__main__":
    main()