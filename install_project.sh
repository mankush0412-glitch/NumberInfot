#!/usr/bin/env bash
set -euo pipefail

mkdir -p /opt/users-api/uploads /opt/users-api/staging /opt/users-api/backups
cd /opt/users-api

python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

cp users-api.service /etc/systemd/system/users-api.service
cp db-manager-bot.service /etc/systemd/system/db-manager-bot.service
cp telegram-bot-api.service /etc/systemd/system/telegram-bot-api.service

systemctl daemon-reload
echo "✅ Project installed. Configure .env and local_bot_api.env before starting services."
