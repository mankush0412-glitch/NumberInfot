import logging
from functools import wraps

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from config import load_config
import key_store

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

config = load_config()
key_store.init_db(config.keys_db_path)

def admin_only(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if not user or user.id not in config.admin_ids:
            if update.effective_message:
                await update.effective_message.reply_text("⛔ Admin only.")
            return
        return await func(update, context)
    return wrapper

@admin_only
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔐 API Key Manager\n\n"
        "Commands:\n"
        "/genkey <name> - Generate new API key\n"
        "/keys - List all keys\n"
        "/key <id> - Show key metadata\n"
        "/disable <id> - Disable a key\n"
        "/enable <id> - Enable a key\n"
        "/rename <id> <new name> - Rename key\n"
        "/delete <id> - Permanently delete key\n"
        "/help - Show commands\n\n"
        "⚠️ Raw API key is shown only once when generated."
    )

@admin_only
async def genkey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = " ".join(context.args).strip()
    if not name:
        await update.message.reply_text("Usage: /genkey <name>\nExample: /genkey main_bot")
        return

    data = key_store.generate_key(
        config.keys_db_path,
        name=name,
        created_by=update.effective_user.id,
    )

    await update.message.reply_text(
        "✅ New API key generated\n\n"
        f"ID: {data['id']}\n"
        f"Name: {data['name']}\n"
        f"Key: `{data['key']}`\n\n"
        "⚠️ Save this key now. It will not be shown again.",
        parse_mode="Markdown",
    )

@admin_only
async def keys(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = key_store.list_keys(config.keys_db_path)
    if not rows:
        await update.message.reply_text("No API keys found.")
        return

    chunks = []
    for row in rows[:100]:
        status = "🟢" if row["enabled"] else "🔴"
        chunks.append(
            f"{status} ID {row['id']} | {row['name']}\n"
            f"Prefix: {row['key_prefix']}… | Uses: {row['use_count']}"
        )

    text = "🔐 API Keys\n\n" + "\n\n".join(chunks)
    if len(rows) > 100:
        text += f"\n\nShowing 100 of {len(rows)} keys."

    await update.message.reply_text(text)

@admin_only
async def key_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /key <id>")
        return
    try:
        key_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid key ID.")
        return

    row = key_store.get_key(config.keys_db_path, key_id)
    if not row:
        await update.message.reply_text("❌ Key not found.")
        return

    status = "Enabled" if row["enabled"] else "Disabled"
    await update.message.reply_text(
        f"🔐 Key #{row['id']}\n\n"
        f"Name: {row['name']}\n"
        f"Status: {status}\n"
        f"Prefix: {row['key_prefix']}…\n"
        f"Created: {row['created_at']}\n"
        f"Last used: {row['last_used_at'] or 'Never'}\n"
        f"Use count: {row['use_count']}"
    )

async def _id_command(update, context, action, label):
    if not context.args:
        await update.message.reply_text(f"Usage: /{label.lower()} <id>")
        return
    try:
        key_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid key ID.")
        return

    ok = action(config.keys_db_path, key_id)
    if ok:
        await update.message.reply_text(f"✅ Key #{key_id} {label.lower()}d.")
    else:
        await update.message.reply_text("❌ Key not found.")

@admin_only
async def disable(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _id_command(update, context, key_store.disable_key, "Disable")

@admin_only
async def enable(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _id_command(update, context, key_store.enable_key, "Enable")

@admin_only
async def delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _id_command(update, context, key_store.delete_key, "Delete")

@admin_only
async def rename(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /rename <id> <new name>")
        return
    try:
        key_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid key ID.")
        return

    new_name = " ".join(context.args[1:]).strip()
    ok = key_store.rename_key(config.keys_db_path, key_id, new_name)
    if ok:
        await update.message.reply_text(f"✅ Key #{key_id} renamed to: {new_name}")
    else:
        await update.message.reply_text("❌ Key not found.")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.exception("Unhandled error", exc_info=context.error)

def main():
    app = Application.builder().token(config.bot_token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(CommandHandler("genkey", genkey))
    app.add_handler(CommandHandler("keys", keys))
    app.add_handler(CommandHandler("key", key_info))
    app.add_handler(CommandHandler("disable", disable))
    app.add_handler(CommandHandler("enable", enable))
    app.add_handler(CommandHandler("rename", rename))
    app.add_handler(CommandHandler("delete", delete))
    app.add_error_handler(error_handler)

    logger.info("API Manager Bot starting...")
    app.run_polling()

if __name__ == "__main__":
    main()
