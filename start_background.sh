#!/usr/bin/env bash
set -euo pipefail
BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$BASE_DIR"
mkdir -p logs

if [ -f manager.pid ] && kill -0 "$(cat manager.pid)" 2>/dev/null; then
  echo "Already running PID $(cat manager.pid)"
  exit 0
fi

if [ ! -d venv ]; then
  python3 -m venv venv
fi
source venv/bin/activate
pip install -r requirements.txt >/dev/null

nohup "$BASE_DIR/venv/bin/python" "$BASE_DIR/manager.py" > "$BASE_DIR/logs/manager.log" 2>&1 &
echo $! > manager.pid
echo "✅ Started PID $(cat manager.pid)"
echo "Logs: $BASE_DIR/logs/manager.log"
