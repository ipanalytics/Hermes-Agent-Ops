#!/bin/bash
# Обновление Hermes ПОД SYSTEMD (mynet-agent-gateway/dashboard.service).
# Управление компонентами — ТОЛЬКО через systemctl, никаких `hermes gateway
# restart` и никаких ad-hoc-подъёмов dashboard (это давало transient cron-scope
# и "mixed sys.modules" — инцидент 06-07.09.2026).
# Первый вызов мгновенно уходит в отвязанный режим (setsid) и возвращается.
#
# Порядок --detached:
#   1) пауза сторожу (watchdog);
#   2) systemctl stop dashboard  -> update не увидит процесс и НЕ поднимет его
#      ad-hoc (он считает dashboard "manual-serve");
#   3) hermes update --yes       -> код/venv обновлены (гейтвей сам не
#      рестартится: sudo недоступен, update печатает подсказку — это ок);
#   4) systemctl restart gateway + systemctl start dashboard (polkit-грант);
#   5) проверка heartbeat/юнитов, ✅/❌ в топик «Система» (30), снятие паузы.
H=/home/hermes/.hermes
VENV="$H/hermes-agent/venv/bin"
PAUSE="$H/state/gateway_watchdog.paused"
LOG="$H/logs/hermes-update.log"
RL="$H/logs/update-run.log"
GW=mynet-agent-gateway.service
DASH=mynet-agent-dashboard.service
TOKEN_LINE=$(grep -E '^TELEGRAM_BOT_TOKEN=' "$H/.env" 2>/dev/null | head -1)

send_tg() {
  [ -z "$TOKEN_LINE" ] && return
  TOKEN=${TOKEN_LINE#TELEGRAM_BOT_TOKEN=}
  curl -s -X POST "https://api.telegram.org/bot${TOKEN}/sendMessage" \
    --data-urlencode "chat_id="${OPS_CHAT_ID}"" \
    --data-urlencode "message_thread_id="${OPS_THREAD_ID}"" \
    --data-urlencode "text=$1" >/dev/null 2>&1
}

if [ "${1:-}" != "--detached" ]; then
  # защита от дублей
  if pgrep -f 'hermes-update-run\.sh --detached' >/dev/null 2>&1; then
    echo "обновление уже запущено — жду."
    exit 0
  fi
  setsid nohup bash -c "exec bash '$0' --detached" >> "$RL" 2>&1 < /dev/null &
  echo "обновление запущено в фоне (pid $!) — переживёт рестарт гейтвея."
  exit 0
fi

# ===== --detached =====
echo "=== update-run started $(date '+%F %T') ===" >> "$RL"
touch "$PAUSE"

# dashboard придержать, чтобы update не поднял его ad-hoc как manual-serve
systemctl stop "$DASH" >> "$RL" 2>&1
echo "dashboard остановлен (для чистого рестарта юнита)" >> "$RL"

"$VENV/hermes" update --yes >> "$LOG" 2>&1
RC=$?
echo "=== hermes update rc=$RC $(date '+%F %T') ===" >> "$RL"

# рестарт/подъём ТОЛЬКО через systemd (hermes-юзеру разрешено polkit-правилом;
# если denied — юниты останутся в прежнем состоянии, ниже будет ❌)
systemctl restart "$GW" >> "$RL" 2>&1; GR=$?
systemctl start "$DASH" >> "$RL" 2>&1; DS=$?
echo "=== restart gw rc=$GR, start dash rc=$DS $(date '+%F %T') ===" >> "$RL"

rm -f "$PAUSE"

# проверка здоровья
sleep 45
NOW=$(date +%s)
HB=$(stat -c %Y "$H/state/gateway.heartbeat" 2>/dev/null)
HBOK="STALE"
if [ -n "$HB" ] && [ $((NOW - HB)) -lt 120 ]; then HBOK="ok"; fi
GWACT=$(systemctl is-active "$GW" 2>/dev/null || echo unknown)
DASHACT=$(systemctl is-active "$DASH" 2>/dev/null || echo unknown)
HEAD=$(git -C "$H/hermes-agent" rev-parse --short HEAD 2>/dev/null)

if [ "$GWACT" = "active" ] && [ "$HBOK" = "ok" ] && [ "$DASHACT" = "active" ]; then
  STATUS_LINE="✅ Hermes обновлён: git $HEAD, rc=$RC, gateway=$GWACT (heartbeat=$HBOK), dashboard=$DASHACT ($(date '+%d.%m %H:%M'))"
else
  STATUS_LINE="❌ Hermes update: git $HEAD rc=$RC, gateway=$GWACT (heartbeat=$HBOK), dashboard=$DASHACT (restart rc=$GR/$DS) — нужен root: systemctl restart $GW && systemctl start $DASH"
fi
echo "$STATUS_LINE" >> "$RL"
send_tg "$STATUS_LINE"
exit 0
