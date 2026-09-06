#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gateway_supervisor.py — external supervisor for an LLM agent gateway.

Why external? An agent gateway cannot reliably heal itself:
  * processes spawned from the agent's own terminal die when the gateway
    restarts (observed twice: a wrapper that restarted the gateway never
    finished its own cleanup);
  * scheduler jobs that restart the gateway are usually blocked by policy
    scanners (protection against restart loops) — the sanctioned path lives
    OUTSIDE the gateway.

This daemon (start detached with setsid) treats two failure classes:
  1) heartbeat file stale (> --hb-stale seconds)   -> process dead or hung
  2) fresh fatal marker in the logs                -> e.g. "deleted state.db-wal"
     (a race that makes the gateway refuse every new write while the process
      itself stays alive: the bot looks dead but `ps` shows it running)

Action: run --restart-cmd, throttled (--cooldown seconds, max --max-per-hour
per hour). Beyond the cap it escalates "manual restore needed" and NEVER
auto-restores state on its own.

Maintenance pause: create the pause file before manual work/updates; the
supervisor clears a *forgotten* pause after ~3 min (when no update process is
running) and alerts. Telegram alerts are sent directly via the Bot API.

Usage:
  gateway_supervisor.py --supervise \\
      --state-dir /var/lib/agent/state --log-dir /var/lib/agent/logs \\
      --heartbeat gateway.heartbeat --restart-cmd "/usr/bin/systemctl restart agent-gw" \\
      --tg-chat -1001234567890 --tg-thread 30 --tg-token-env TELEGRAM_BOT_TOKEN
Guard cron (separate, scheduler-owned): re-spawn this daemon if it died —
its PID dies with every gateway restart, that is the design, not a bug.
"""
import argparse
import datetime
import os
import re
import subprocess
import time
import urllib.parse
import urllib.request


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--supervise", action="store_true", help="run as daemon loop")
    p.add_argument("--state-dir", required=True)
    p.add_argument("--log-dir", required=True)
    p.add_argument("--heartbeat", default="gateway.heartbeat")
    p.add_argument("--pause-file", default="gateway_supervisor.paused")
    p.add_argument("--pid-file", default="gateway_supervisor.pid")
    p.add_argument("--restart-cmd", required=True, help="shell command to restart the gateway")
    p.add_argument("--fatal-pattern", default=r"deleted .*\.db-wal", help="regex matched against log tails")
    p.add_argument("--log-files", nargs="*", default=["errors.log", "agent.log"])
    p.add_argument("--hb-stale", type=int, default=300)
    p.add_argument("--fatal-fresh", type=int, default=240, help="fatal line fresher than this counts")
    p.add_argument("--cooldown", type=int, default=600)
    p.add_argument("--max-per-hour", type=int, default=3)
    p.add_argument("--loop-s", type=int, default=120)
    p.add_argument("--tg-chat", default=None)
    p.add_argument("--tg-thread", default=None)
    p.add_argument("--tg-token-env", default="TELEGRAM_BOT_TOKEN")
    p.add_argument("--update-proc-pattern", default="agent update --yes",
                   help="if this process is running, a forgotten pause is NOT cleared")
    return p.parse_args()


def log(msg: str) -> None:
    print(f"{datetime.datetime.now():%F %T} {msg}", flush=True)


def read_env_token(varname: str) -> str | None:
    return os.environ.get(varname) or None


def tg_send(text: str, args) -> None:
    token = read_env_token(args.tg_token_env)
    if not token or not args.tg_chat:
        return
    try:
        data = urllib.parse.urlencode({"chat_id": args.tg_chat,
                                       "text": text,
                                       **({"message_thread_id": args.tg_thread} if args.tg_thread else {})}).encode()
        req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=data)
        urllib.request.urlopen(req, timeout=20).read()
        log(f"alert sent: {text[:80]}")
    except Exception as e:
        log(f"tg send error: {e}")


class Supervisor:
    def __init__(self, args):
        self.a = args
        self.heartbeat = os.path.join(args.state_dir, args.heartbeat)
        self.pause = os.path.join(args.state_dir, args.pause_file)
        self.state_f = os.path.join(args.state_dir, "gateway_supervisor.json")
        self.pid_f = os.path.join(args.state_dir, args.pid_file)
        self.logs = args.log_dir
        self.last_restart = 0.0
        self.restarts_hour = []  # timestamps

    # ---- signals -------------------------------------------------------
    def heartbeat_age(self) -> float:
        try:
            return time.time() - os.path.getmtime(self.heartbeat)
        except OSError:
            return 1e9

    def fresh_fatal(self) -> bool:
        pat = re.compile(r"^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}:\d{2})")
        rx = re.compile(self.a.fatal_pattern)
        newest = 0.0
        for name in self.a.log_files:
            path = os.path.join(self.logs, name)
            if not os.path.exists(path):
                continue
            try:
                with open(path, encoding="utf-8", errors="replace") as f:
                    f.seek(0, 2)
                    size = f.tell()
                    f.seek(max(0, size - 300_000))
                    for line in f:
                        if not rx.search(line):
                            continue
                        m = pat.search(line)
                        if not m:
                            continue
                        try:
                            ts = datetime.datetime.strptime(m.group(1) + " " + m.group(2),
                                                            "%Y-%m-%d %H:%M:%S").timestamp()
                        except ValueError:
                            continue
                        newest = max(newest, ts)
            except OSError:
                continue
        return (time.time() - newest) < self.a.fatal_fresh

    def update_running(self) -> bool:
        """An update process is running -> never touch a forgotten pause."""
        try:
            r = subprocess.run(["pgrep", "-f", self.a.update_proc_pattern],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
            return r.returncode == 0
        except Exception:
            return True  # could not check -> do not touch the pause

    # ---- pause handling ------------------------------------------------
    def pause_clearable(self) -> bool:
        """Pause older than ~3 min with no update running -> forgotten -> clear."""
        try:
            age = time.time() - os.path.getmtime(self.pause)
        except OSError:
            return False
        return age > 180 and not self.update_running()

    # ---- restart -------------------------------------------------------
    def can_restart(self) -> bool:
        now = time.time()
        self.restarts_hour = [t for t in self.restarts_hour if now - t < 3600]
        if self.last_restart and now - self.last_restart < self.a.cooldown:
            return False
        return len(self.restarts_hour) < self.a.max_per_hour

    def restart(self) -> bool:
        try:
            subprocess.run(self.a.restart_cmd, shell=True, timeout=120)
            self.last_restart = time.time()
            self.restarts_hour.append(self.last_restart)
            log("gateway restarted")
            return True
        except Exception as e:
            log(f"restart failed: {e}")
            return False

    def unhealthy_reason(self) -> str | None:
        age = self.heartbeat_age()
        if age > self.a.hb_stale:
            return f"heartbeat stale ({int(age)}s)"
        if self.fresh_fatal():
            return "fresh fatal marker in logs (wal race signature)"
        return None

    def loop(self):
        os.makedirs(self.a.state_dir, exist_ok=True)
        with open(self.pid_f, "w") as f:
            f.write(str(os.getpid()))
        log(f"supervisor started pid={os.getpid()} heartbeat={self.heartbeat}")
        while True:
            try:
                if os.path.exists(self.pause):
                    if self.pause_clearable():
                        os.remove(self.pause)
                        tg_send("supervisor: cleared forgotten maintenance pause", self.a)
                    time.sleep(self.a.loop_s)
                    continue
                reason = self.unhealthy_reason()
                if reason and self.can_restart():
                    tg_send(f"gateway unhealthy ({reason}) — restarting", self.a)
                    if not self.restart():
                        continue
                    # Give it a moment, then confirm.
                    time.sleep(20)
                    if self.heartbeat_age() > self.a.hb_stale:
                        if len(self.restarts_hour) >= self.a.max_per_hour:
                            tg_send("still unhealthy after max restarts/hour — manual restore needed (no auto-restore)", self.a)
                        else:
                            tg_send("still unhealthy after restart — will retry within cooldown", self.a)
                    else:
                        tg_send("gateway recovered after restart", self.a)
            except Exception as e:
                log(f"loop error: {e}")
            time.sleep(self.a.loop_s)


if __name__ == "__main__":
    args = parse_args()
    if args.supervise:
        Supervisor(args).loop()
    else:
        print("run with --supervise (detached, e.g. via setsid). See module docstring.")
