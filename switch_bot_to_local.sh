#!/usr/bin/env bash
set -euo pipefail

cd /opt/users-api
if [ ! -f local_bot_api.env ]; then
  echo "❌ /opt/users-api/local_bot_api.env missing"
  exit 1
fi
set -a
source local_bot_api.env
set +a

if [ -z "${BOT_TOKEN:-}" ]; then
  echo "❌ BOT_TOKEN missing in local_bot_api.env"
  exit 1
fi

echo "Calling Telegram cloud Bot API logOut..."
curl -fsS "https://api.telegram.org/bot${BOT_TOKEN}/logOut"
echo
echo "Starting local Bot API server..."
systemctl restart telegram-bot-api
systemctl enable telegram-bot-api
systemctl status telegram-bot-api --no-pager
