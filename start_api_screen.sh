#!/usr/bin/env bash
set -euo pipefail
BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$BASE_DIR"

API_SCREEN="${API_SCREEN:-users-api}"
API_HOST="${API_HOST:-0.0.0.0}"
API_PORT="${API_PORT:-8000}"
API_WORKERS="${API_WORKERS:-2}"
LOG_DIR="$BASE_DIR/logs"
mkdir -p "$LOG_DIR"

if [ -f "$BASE_DIR/.env" ]; then
  _host="$(grep -E '^API_HOST=' "$BASE_DIR/.env" | tail -1 | cut -d= -f2- | tr -d '\r' || true)"
  _port="$(grep -E '^API_PORT=' "$BASE_DIR/.env" | tail -1 | cut -d= -f2- | tr -d '\r' || true)"
  _workers="$(grep -E '^API_WORKERS=' "$BASE_DIR/.env" | tail -1 | cut -d= -f2- | tr -d '\r' || true)"
  [ -n "$_host" ] && API_HOST="$_host"
  [ -n "$_port" ] && API_PORT="$_port"
  [ -n "$_workers" ] && API_WORKERS="$_workers"
fi

# 127.0.0.1 would prevent access from another server; screen launcher defaults public.
if [ "$API_HOST" = "127.0.0.1" ] || [ "$API_HOST" = "localhost" ]; then
  API_HOST="0.0.0.0"
fi

screen -S "$API_SCREEN" -X quit >/dev/null 2>&1 || true
sleep 1

screen -dmS "$API_SCREEN" bash -lc \
  "cd '$BASE_DIR' && '$BASE_DIR/venv/bin/uvicorn' fastapi_app:app --host '$API_HOST' --port '$API_PORT' --workers '$API_WORKERS' 2>&1 | tee -a '$LOG_DIR/users-api.log'"
