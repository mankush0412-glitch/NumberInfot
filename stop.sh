#!/usr/bin/env bash
set -euo pipefail
BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$BASE_DIR"

if [ ! -f manager.pid ]; then
  echo "No manager.pid"
  exit 0
fi

PID="$(cat manager.pid)"
if kill -0 "$PID" 2>/dev/null; then
  kill "$PID"
  echo "✅ Stopped PID $PID"
fi
rm -f manager.pid
