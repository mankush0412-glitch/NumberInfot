#!/usr/bin/env bash
set -euo pipefail
BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$BASE_DIR"

API_SCREEN="users-api"
MANAGER_SCREEN="db-manager"
LOG_DIR="$BASE_DIR/logs"
mkdir -p "$LOG_DIR"

if [ ! -f .env ]; then
  cp .env.example .env
  echo "❌ .env created. Fill it first: nano $BASE_DIR/.env"
  exit 1
fi

if ! command -v screen >/dev/null 2>&1; then
  echo "📦 Installing screen..."
  apt-get update -qq
  DEBIAN_FRONTEND=noninteractive apt-get install -y screen >/dev/null
fi

if [ ! -d venv ]; then
  echo "📦 Creating Python venv..."
  python3 -m venv venv
  ./venv/bin/python -m pip install --upgrade pip
fi

# Ensure project dependencies exist. Quiet when already satisfied.
./venv/bin/python -m pip install -q -r requirements.txt

# Avoid port/session conflicts with old systemd deployment.
for svc in users-api db-manager-bot api-manager-bot; do
  systemctl stop "$svc" >/dev/null 2>&1 || true
done

# Stop only our old screen sessions, if any.
screen -S "$API_SCREEN" -X quit >/dev/null 2>&1 || true
screen -S "$MANAGER_SCREEN" -X quit >/dev/null 2>&1 || true
sleep 1

# API in its own screen.
API_RUN_MODE=screen "$BASE_DIR/start_api_screen.sh"

# Manager bot in its own screen. API_RUN_MODE tells /activate and /rollback
# to restart the screen API rather than systemd.
screen -dmS "$MANAGER_SCREEN" bash -lc \
  "cd '$BASE_DIR' && export API_RUN_MODE=screen && '$BASE_DIR/venv/bin/python' manager.py 2>&1 | tee -a '$LOG_DIR/db-manager.log'"

API_PORT="$(grep -E '^API_PORT=' .env | tail -1 | cut -d= -f2- | tr -d '\r' || true)"
API_PORT="${API_PORT:-8000}"

# Wait briefly for FastAPI to become ready.
READY=0
for _ in $(seq 1 20); do
  if curl -fsS --max-time 2 "http://127.0.0.1:${API_PORT}/" >/dev/null 2>&1; then
    READY=1
    break
  fi
  sleep 1
done

PUBLIC_IP="$(curl -4 -fsS --max-time 5 https://api.ipify.org 2>/dev/null || true)"
if [ -z "$PUBLIC_IP" ]; then
  PUBLIC_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
fi

printf '\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n'
echo "✅ DB API stack started"
echo "🟢 API screen:     $API_SCREEN"
echo "🟢 Manager screen: $MANAGER_SCREEN"
if [ "$READY" -eq 1 ]; then
  echo "✅ API health:     OK"
else
  echo "⚠️ API health:     not ready yet (check log below)"
fi

echo "🏠 Local URL:      http://127.0.0.1:${API_PORT}"
if [ -n "$PUBLIC_IP" ]; then
  echo "🌐 Public URL:     http://${PUBLIC_IP}:${API_PORT}"
  echo "🔗 Health link:    http://${PUBLIC_IP}:${API_PORT}/"
else
  echo "🌐 Public URL:     Could not detect public IP"
fi
printf '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n'
echo "📺 API console:     screen -r $API_SCREEN"
echo "📺 Manager console: screen -r $MANAGER_SCREEN"
echo "📄 API log:         tail -f $LOG_DIR/users-api.log"
echo "📄 Manager log:     tail -f $LOG_DIR/db-manager.log"
echo "📋 Screens:         screen -ls"
