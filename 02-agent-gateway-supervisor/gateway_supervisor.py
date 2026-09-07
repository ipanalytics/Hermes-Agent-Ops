#!/home/hermes/.hermes/hermes-agent/venv/bin/python
# -*- coding: utf-8 -*-
"""
Внешний сторож-супервизор гейтвея Hermes ПОД SYSTEMD (mynet-agent-gateway.service).

НИКОГДА не запускает `hermes gateway restart`/`gateway run` (двойное управление
systemd + hermes CLI = инцидент 07.09.2026: "Gateway already running", юнит в failed,
зависшие restart-процессы, державшие state.db-wal/-shm, отказ записи сессий).

Лечение нездоровья — ТОЛЬКО systemctl:
  1) `systemctl restart mynet-agent-gateway.service` (polkit: hermes разрешён на
     mynet-agent-gateway/.dashboard.service — правило 49-mynet-hermes.rules);
  2) если systemctl denied/недоступен — фолбэк без root: SIGTERM основному PID
     юнита, через TERM_GRACE_S — SIGKILL; systemd Restart=on-failure поднимет
     процесс сам (SIGKILL => exit != 0 => рестарт).

Сигналы нездоровья (греп хвостов errors.log/agent.log, свежесть < SIGNAL_FRESH_S):
  1) "deleted state.db-wal" FATAL — удалённые sidecar'ы при живом гейтвее;
  2) отказ записи сессий: "unable to open database file" / "session storage could
     not be written" / "Session DB creation failed" / "Session DB append_message
     failed" (>= SIGNAL_MIN_LINES свежих строк — одиночная случайная не сработает);
  3) heartbeat (state/gateway.heartbeat) старше HB_STALE_S.

Действие: рестарт не чаще 1/COOLDOWN_S, макс MAX_PER_HOUR/час (дальше — эскалация,
БЕЗ авто-restore из бэкапов). Dashboard НЕ поднимаем ad-hoc (это делал баг с
transient cron-scope): юнит mynet-agent-dashboard.service самовосстанавливается
(Restart=on-failure); если он неактивен дольше DASH_INACTIVE_ALERT_S — пытаемся
`systemctl start` и алертим в топик «Система» (30) при отказе.

Запуск (демон):  setsid nohup .../hermes_gateway_watchdog.py --supervise >> logs/gateway_watchdog_supervisor.log 2>&1 &
Пауза (апдейты/ручные работы): touch ~/.hermes/state/gateway_watchdog.paused
(снимается автоматически через 180 с, если апдейт не идёт — см. run_once)
"""
import os, re, sys, time, json, datetime, subprocess, signal, socket, urllib.request, urllib.parse

H = "/home/hermes/.hermes"
LOGS = os.path.join(H, "logs")
STATE = os.path.join(H, "state")
HEARTBEAT = os.path.join(STATE, "gateway.heartbeat")
PAUSE = os.path.join(STATE, "gateway_watchdog.paused")
STATE_F = os.path.join(STATE, "gateway_watchdog.json")
PID_F = os.path.join(STATE, "gateway_watchdog_supervisor.pid")
RESTART_LOG = os.path.join(LOGS, "gateway_watchdog_restart.log")
UNIT_GW = "mynet-agent-gateway.service"
UNIT_DASH = "mynet-agent-dashboard.service"
DASH_SCRIPT = os.path.join(H, "scripts", "hermes-dashboard-start.sh")  # больше НЕ используется для подъёма
CHAT = os.environ.get("OPS_CHAT_ID", "")   # группа (env) — в репо без реальных ID
THREAD = os.environ.get("OPS_THREAD_ID", "")       # топик (env)

HB_STALE_S = 300
SIGNAL_FRESH_S = 240
SIGNAL_MIN_LINES = 2
COOLDOWN_S = 600
MAX_PER_HOUR = 3
LOOP_S = 120
TERM_GRACE_S = 60
DASH_INACTIVE_ALERT_S = 240
_TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}:\d{2})")
# (1) wal-refusal срабатывает от 1 строки; (2) отказы записи — от SIGNAL_MIN_LINES
_PAT_WAL = "deleted state.db-wal"
_PAT_WRITE = (
    "unable to open database file",
    "session storage could not be written",
    "Session DB creation failed",
    "Session DB append_message failed",
)


def log(msg):
    print(f"{datetime.datetime.now():%F %T} {msg}", flush=True)


def tg_send(text: str):
    token = None
    try:
        for line in open(os.path.join(H, ".env"), encoding="utf-8", errors="replace"):
            line = line.strip()
            if line.startswith("TELEGRAM_BOT_TOKEN="):
                token = line.split("=", 1)[1].strip().strip('"').strip("'")
                break
    except Exception as e:
        log(f"токен: {e}")
        return
    if not token:
        log("нет TELEGRAM_BOT_TOKEN в .env")
        return
    try:
        body = urllib.parse.urlencode({
            "chat_id": CHAT, "message_thread_id": THREAD, "text": text,
        }).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage", data=body)
        urllib.request.urlopen(req, timeout=20).read()
        log(f"TG-алерт отправлен: {text[:80]}")
    except Exception as e:
        log(f"TG send err: {e}")


def sh(*args, timeout=30):
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except Exception as e:
        return -1, str(e)


def heartbeat_age():
    try:
        return time.time() - os.path.getmtime(HEARTBEAT)
    except OSError:
        return 1e9


def unit_state(unit):
    rc, _ = sh("systemctl", "is-active", unit)
    return (rc, (rc == 0))


def unit_main_pid(unit):
    rc, out = sh("systemctl", "show", "-p", "MainPID", "--value", unit)
    try:
        return int(out.strip()) if rc == 0 else 0
    except ValueError:
        return 0


def _scan_log_tail(logf, min_ts):
    """Вернуть (число свежих wal-строк, число свежих write-строк) в хвосте файла."""
    p = os.path.join(LOGS, logf)
    if not os.path.exists(p):
        return 0, 0
    wal = write = 0
    try:
        with open(p, encoding="utf-8", errors="replace") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 400_000))
            for line in f:
                if _PAT_WAL not in line and not any(w in line for w in _PAT_WRITE):
                    continue
                m = _TS_RE.search(line)
                if not m:
                    continue
                try:
                    ts = datetime.datetime.strptime(
                        m.group(1) + " " + m.group(2), "%Y-%m-%d %H:%M:%S"
                    ).timestamp()
                except ValueError:
                    continue
                if ts < min_ts:
                    continue
                if _PAT_WAL in line:
                    wal += 1
                else:
                    write += 1
    except OSError:
        pass
    return wal, write


def fresh_store_signal():
    """Свежие (< SIGNAL_FRESH_S) отказы записи/сессий в логах."""
    cutoff = time.time() - SIGNAL_FRESH_S
    wal = write = 0
    for logf in ("errors.log", "agent.log"):
        w, wr = _scan_log_tail(logf, cutoff)
        wal += w
        write += wr
    if wal >= 1:
        return f"wal-refusal (deleted state.db-wal, {wal} свеж.)"
    if write >= SIGNAL_MIN_LINES:
        return f"session-store write failure (unable to open database file / session storage, {write} свеж.)"
    return None


def update_running():
    """Идёт ли сейчас hermes update (тогда паузу не трогаем)."""
    try:
        r = subprocess.run(["pgrep", "-f", "hermes update --yes"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
        return r.returncode == 0
    except Exception:
        return True


def pause_age():
    try:
        return time.time() - os.path.getmtime(PAUSE)
    except OSError:
        return 0.0


def dashboard_up():
    rc, _ = unit_state(UNIT_DASH)
    return rc == 0


def load_state():
    try:
        with open(STATE_F) as f:
            return json.load(f)
    except Exception:
        return {"last": 0.0, "count": 0, "window": 0.0, "restart_pid": 0, "pending": False}


def save_state(st):
    try:
        with open(STATE_F, "w") as f:
            json.dump(st, f)
    except OSError as e:
        log(f"state save err: {e}")


def _rl(msg):
    try:
        with open(RESTART_LOG, "a") as f:
            f.write(f"{datetime.datetime.now():%F %T} {msg}\n")
    except OSError as e:
        log(f"restart-log err: {e}")


def _wait_heartbeat_fresh(timeout_s=150):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if heartbeat_age() <= HB_STALE_S:
            return True
        time.sleep(5)
    return False


def _kill_pid_wait(pid, grace=TERM_GRACE_S):
    """SIGTERM, затем SIGKILL через grace; вернуть True, если процесс умер."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return True
    except OSError:
        return False
    deadline = time.time() + grace
    while time.time() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        time.sleep(2)
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        return True
    except OSError:
        return False
    for _ in range(15):
        time.sleep(2)
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
    return False


def restart_gateway():
    """Вернуть (способ, ok, детали). Способ: systemctl | kill-fallback | failed."""
    _rl("=== restart gateway ===")
    # 1) штатный путь: systemctl (polkit-грант hermes)
    rc, out = sh("systemctl", "restart", UNIT_GW, timeout=90)
    if rc == 0:
        ok = _wait_heartbeat_fresh()
        _rl(f"systemctl restart rc=0 heartbeat_ok={ok}")
        return ("systemctl", ok, f"systemctl restart rc=0, heartbeat={'ok' if ok else 'STALE'}")
    _rl(f"systemctl restart denied/rc={rc}: {out.strip()[:160]} — фолбэк kill")
    # 2) rootless-фолбэк: убить процесс юнита -> systemd Restart=on-failure
    pid = unit_main_pid(UNIT_GW)
    if pid > 0:
        dead = _kill_pid_wait(pid)
        _rl(f"kill pid {pid} dead={dead}")
    ok = _wait_heartbeat_fresh()
    _rl(f"fallback done heartbeat_ok={ok}")
    return ("kill-fallback", ok, f"kill pid {pid} dead={dead}, heartbeat={'ok' if ok else 'STALE'}")


def run_once():
    """Один проход детекции. Возвращает pid запущенного рестарта (0 если нет)."""
    if os.path.exists(PAUSE):
        if update_running():
            return 0
        p_age = pause_age()
        if p_age > 180:
            try:
                os.remove(PAUSE)
            except OSError:
                pass
            tg_send("⚠ Hermes-watchdog: апдейт оставил зависшую паузу — снял её, сторож снова активен.")
            log(f"зависшая пауза ({p_age:.0f}с) снята")
        return 0
    age = heartbeat_age()
    sig = fresh_store_signal()
    st = load_state()
    healthy = age <= HB_STALE_S and not sig
    if healthy:
        # dashboard: не поднимаем ad-hoc — только контроль через systemctl,
        # с порогом неактивности DASH_INACTIVE_ALERT_S (троттлинг start-попыток)
        if not dashboard_up():
            st.setdefault("dash_down_since", time.time())
            down_for = time.time() - st["dash_down_since"]
            if down_for >= DASH_INACTIVE_ALERT_S:
                rc, _ = sh("systemctl", "start", UNIT_DASH, timeout=60)
                if rc == 0:
                    st["dash_down_since"] = 0.0
                    tg_send("🔄 Hermes-watchdog: dashboard-юнит был неактивен — `systemctl start` ok.")
                    log("dashboard unit неактивен — systemctl start ok")
                else:
                    tg_send(f"⚠ Hermes-watchdog: dashboard-юнит неактивен {down_for:.0f}с и не стартует (rc={rc}) — нужен root: `systemctl start {UNIT_DASH}`")
                    log(f"dashboard unit start rc={rc}")
        else:
            st["dash_down_since"] = 0.0
        save_state(st)
        if st.get("pending"):
            st["pending"] = False
            st["count"] = 0
            st["window"] = 0.0
            save_state(st)
            tg_send(f"✅ Hermes-гейтвей восстановился сам ({datetime.datetime.now():%H:%M:%S}), всё работает.")
            log("здоров; восстановление подтверждено")
        return 0
    reason = sig or f"heartbeat stale ({age:.0f}с)"
    t = time.time()
    if st.get("window", 0) and t - st["window"] > 3600:
        st = {"last": 0.0, "count": 0, "window": t, "restart_pid": 0, "pending": False}
    st.setdefault("window", t)
    if st.get("count", 0) >= MAX_PER_HOUR:
        log(f"ЭСКАЛАЦИЯ: {st['count']} рестартов/час, стоп")
        tg_send(
            f"🚨 Hermes-watchdog: {st['count']} рестартов за час — гейтвей не поднимается.\n"
            f"state.db, вероятно, повреждена: нужен restore из бэкапа "
            f"(~/.hermes/backups/hermes/daily/...) + ручной root: systemctl restart {UNIT_GW}."
        )
        return 0
    if t - st.get("last", 0) < COOLDOWN_S:
        log(f"нездорово ({reason}), но рестарт был {t-st['last']:.0f}с назад — жду")
        return 0
    st["count"] = st.get("count", 0) + 1
    st["last"] = t
    st["pending"] = True
    method, ok, detail = restart_gateway()
    st["restart_pid"] = 0
    save_state(st)
    log(f"НЕЗДОРОВО ({reason}) -> рестарт #{st['count']} [{method}], ok={ok}")
    tg_send(
        f"⚠ Hermes-гейтвей перезапускается watchdog'ом ({datetime.datetime.now():%H:%M:%S}): {reason}. "
        f"Попытка {st['count']}/3. Способ: {method}. {detail}"
    )
    return 0


def supervise():
    if os.path.exists(PID_F):
        try:
            with open(PID_F) as f:
                old = int(f.read().strip() or "0")
            os.kill(old, 0)
            log(f"супервизор уже работает (pid {old}) — выход")
            sys.exit(0)
        except (ProcessLookupError, ValueError, OSError):
            pass
    with open(PID_F, "w") as f:
        f.write(str(os.getpid()))
    log(f"супервизор запущен pid={os.getpid()} (systemd-режим, unit={UNIT_GW})")
    while True:
        try:
            run_once()
        except Exception as e:
            log(f"ошибка цикла: {e}")
        time.sleep(LOOP_S)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--supervise":
        supervise()
    else:
        run_once()
        log("разовый проход завершён")
