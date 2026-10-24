# Telegram DB Manager + Local Bot API + Protected FastAPI

This package manages a large SQLite database through an admin-only Telegram bot.

## What it does

1. Uses a self-hosted Local Telegram Bot API server.
2. Admin forwards/sends already-uploaded large split files to the manager bot.
3. The manager saves each `data_db.part.xx` file to `/opt/users-api/uploads`.
4. `/parts` checks the sequence.
5. `/installparts` streams all parts together, gzip-decompresses, tar-extracts to staging, and validates SQLite.
6. `/activate CONFIRM` backs up the current production database, replaces it with the validated staged DB, and restarts FastAPI.
7. The same bot manages API keys.

The Local Telegram Bot API supports unlimited downloads and uploads up to 2000 MB. It must be used instead of the normal cloud Bot API for large files.

## Important prerequisites

You need:

- Ubuntu VPS
- root access
- enough disk space for:
  - uploaded split parts
  - extracted DB
  - one backup
- Telegram `api_id` and `api_hash` from `https://my.telegram.org`
- a manager bot token
- your Telegram numeric user ID for `ADMIN_IDS`

For a very large DB, budget several times the final DB size in free disk space.

## 1. Copy project to VPS

Place all files in:

```bash
/opt/users-api/
```

Then:

```bash
cd /opt/users-api
chmod +x *.sh
cp .env.example .env
cp local_bot_api.env.example local_bot_api.env
nano .env
nano local_bot_api.env
```

Example `.env`:

```env
BOT_TOKEN=YOUR_MANAGER_BOT_TOKEN
ADMIN_IDS=YOUR_TELEGRAM_ID
LOCAL_BOT_API_URL=http://127.0.0.1:8081
UPLOADS_DIR=/opt/users-api/uploads
STAGING_DIR=/opt/users-api/staging
DB_PATH=/opt/users-api/hitek2.db
BACKUPS_DIR=/opt/users-api/backups
KEYS_DB_PATH=/opt/users-api/api_keys.db
API_SERVICE=users-api
EXPECTED_TABLE=users
```

Example `local_bot_api.env`:

```env
TELEGRAM_API_ID=123456
TELEGRAM_API_HASH=your_api_hash
BOT_TOKEN=YOUR_MANAGER_BOT_TOKEN
```

Protect secrets:

```bash
chmod 600 .env local_bot_api.env
```

## 2. Build official Telegram Bot API server

```bash
./build_local_bot_api.sh
```

This builds the open-source `tdlib/telegram-bot-api` server from source.

## 3. Install Python project + systemd units

```bash
apt-get update
apt-get install -y python3 python3-pip python3-venv curl sqlite3
./install_project.sh
```

## 4. Switch the manager bot from cloud Bot API to local Bot API

Telegram requires calling `logOut` before using the bot with a Local Bot API server.

```bash
./switch_bot_to_local.sh
```

After `logOut`, Telegram says you can immediately use the local server, but cloud login is unavailable for 10 minutes.

Check local API:

```bash
curl "http://127.0.0.1:8081/botYOUR_BOT_TOKEN/getMe"
```

## 5. Start API and manager bot

```bash
systemctl enable --now users-api
systemctl enable --now db-manager-bot
```

Check:

```bash
systemctl status telegram-bot-api
systemctl status users-api
systemctl status db-manager-bot
```

Logs:

```bash
journalctl -u telegram-bot-api -f
journalctl -u users-api -f
journalctl -u db-manager-bot -f
```

## 6. Telegram workflow

Open the manager bot from the admin account.

```text
/start
```

Forward/send each split file to the bot:

```text
data_db.part.aa
data_db.part.ab
data_db.part.ac
...
```

The bot saves the document on the VPS.

Check:

```text
/parts
```

When all contiguous parts are present:

```text
/installparts
```

This does NOT replace the live DB. It only extracts and validates a staged database.

Check:

```text
/staged
/dbstatus
```

Activate:

```text
/activate CONFIRM
```

The bot:
- validates staged DB again
- backs up current production DB
- replaces `hitek2.db`
- restarts `users-api`

## 7. API key management

Generate one key per client/bot:

```text
/genkey main_lookup_bot
/genkey test_bot
```

List:

```text
/keys
```

Disable:

```text
/disable 2
```

Enable:

```text
/enable 2
```

Delete:

```text
/deletekey 2 CONFIRM
```

Raw keys are not stored; only SHA-256 hashes are stored.

Client bot uses:

```env
API_URL=http://127.0.0.1:8000
API_KEY=THE_GENERATED_KEY
```

If the lookup bot is on a different server, expose FastAPI through HTTPS/Nginx and use the HTTPS URL instead.

## 8. Rollback

Backups are in:

```bash
/opt/users-api/backups
```

List:

```bash
ls -lh /opt/users-api/backups
```

Restore from Telegram:

```text
/rollback hitek2_20260906_010203.db.bak CONFIRM
```

## Security

- Manager commands are restricted to `ADMIN_IDS`.
- FastAPI binds to `127.0.0.1` by default.
- API keys can be independently revoked.
- Database activation requires explicit `CONFIRM`.
- Archive extraction blocks path traversal.
- API opens production DB read-only.
- Keep `.env`, `local_bot_api.env`, database files, and backups private.

## Notes on large files

Local Bot API official capabilities:
- cloud Bot API download: 20 MB
- Local Bot API download: no size limit
- Local Bot API upload: up to 2000 MB

If a split part itself exceeds 2000 MB and you are trying to upload it newly through the bot, split it smaller. For an already-existing Telegram file, Local Bot API's download capability is the important part.

## Test API

Generate key using `/genkey test`.

Then on VPS:

```bash
curl -H "X-API-Key: YOUR_KEY" http://127.0.0.1:8000/stats
```

Lookup:

```bash
curl -H "X-API-Key: YOUR_KEY" \
  http://127.0.0.1:8000/user/9876543210
```
