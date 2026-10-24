import asyncio
import logging
import re
import shutil
from functools import wraps
from pathlib import Path

from pyrogram import Client, filters
from pyrogram.types import Message

from config import load_config
import key_store
from database_installer import (
    get_parts,
    validate_part_sequence,
    safe_extract_stream,
    find_sqlite_candidate,
    production_status,
    activate_database,
)

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

cfg = load_config()

if not cfg.api_id:
    raise RuntimeError("TELEGRAM_API_ID missing in .env")
if not cfg.api_hash:
    raise RuntimeError("TELEGRAM_API_HASH missing in .env")

for d in (cfg.uploads_dir, cfg.staging_dir, cfg.backups_dir):
    d.mkdir(parents=True, exist_ok=True)

key_store.init_db(cfg.keys_db)

STATE_FILE = cfg.staging_dir.parent / ".staged_db_path"
SESSION_DIR = Path(__file__).resolve().parent

app = Client(
    "db_manager_bot",
    api_id=cfg.api_id,
    api_hash=cfg.api_hash,
    bot_token=cfg.bot_token,
    workdir=str(SESSION_DIR),
)


def args_of(message: Message) -> list[str]:
    command = message.command or []
    return command[1:]


def admin_only(func):
    @wraps(func)
    async def wrapper(client: Client, message: Message):
        user = message.from_user
        if not user or user.id not in cfg.admin_ids:
            await message.reply_text("⛔ Admin only.")
            return
        try:
            return await func(client, message)
        except Exception as e:
            logger.exception("Handler failed: %s", func.__name__)
            await message.reply_text(f"❌ Error: {type(e).__name__}: {e}")
    return wrapper


def human_size(n: int):
    units = ["B", "KB", "MB", "GB", "TB"]
    x = float(n)
    for u in units:
        if x < 1024 or u == units[-1]:
            return f"{x:.2f} {u}"
        x /= 1024


def safe_filename(name: str):
    name = Path(name).name
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name)
    return name[:240] or "telegram_file.bin"


@app.on_message(filters.command(["start", "help"]))
@admin_only
async def start(client: Client, message: Message):
    await message.reply_text(
        "🗄 Database + API Manager\n\n"
        "FILE COMMANDS\n"
        "Send/forward a document here → saves it in uploads\n"
        "/parts - list uploaded split parts\n"
        "/cleanuploads CONFIRM - delete uploaded parts\n"
        "/installparts - join/decompress/extract/validate into staging\n"
        "/dbstatus - production DB status\n"
        "/staged - staged DB status\n"
        "/activate CONFIRM - backup old DB, activate staged DB, restart API\n"
        "/rollback <backup_filename> CONFIRM - restore backup\n\n"
        "API KEY COMMANDS\n"
        "/genkey <name>\n"
        "/keys\n"
        "/disable <id>\n"
        "/enable <id>\n"
        "/deletekey <id> CONFIRM\n\n"
        "⚠️ Only ADMIN_IDS can use this bot."
    )


@app.on_message(filters.document)
@admin_only
async def receive_document(client: Client, message: Message):
    doc = message.document
    if not doc:
        return

    name = safe_filename(doc.file_name or f"{doc.file_unique_id}.bin")
    destination = cfg.uploads_dir / name

    await message.reply_text(
        f"⬇️ Downloading: {name}\nSize: {human_size(doc.file_size or 0)}"
    )

    try:
        saved = await message.download(file_name=str(destination))
        saved_path = Path(saved) if saved else destination

        if saved_path != destination and saved_path.exists():
            await asyncio.to_thread(shutil.move, str(saved_path), str(destination))

        await message.reply_text(
            f"✅ Saved\n{name}\n{human_size(destination.stat().st_size)}\n"
            f"Path: {destination}"
        )
    except Exception as e:
        logger.exception("File save failed")
        await message.reply_text(f"❌ File save failed: {type(e).__name__}: {e}")


@app.on_message(filters.command("parts"))
@admin_only
async def parts(client: Client, message: Message):
    ps = get_parts(cfg.uploads_dir)
    if not ps:
        await message.reply_text("No .part.xx files found.")
        return

    ok, msg = validate_part_sequence(ps)
    lines = [f"{'✅' if ok else '⚠️'} {msg}", ""]
    total = 0

    for p in ps:
        size = p.stat().st_size
        total += size
        lines.append(f"{p.name} — {human_size(size)}")

    lines.append(f"\nTotal: {human_size(total)}")
    await message.reply_text("\n".join(lines))


@app.on_message(filters.command("cleanuploads"))
@admin_only
async def cleanuploads(client: Client, message: Message):
    args = args_of(message)
    if not args or args[0] != "CONFIRM":
        await message.reply_text("Use: /cleanuploads CONFIRM")
        return

    removed = 0
    for p in cfg.uploads_dir.iterdir():
        if p.is_file():
            p.unlink()
            removed += 1

    await message.reply_text(f"✅ Removed {removed} uploaded files.")


@app.on_message(filters.command("installparts"))
@admin_only
async def installparts(client: Client, message: Message):
    ps = get_parts(cfg.uploads_dir)
    ok, msg = validate_part_sequence(ps)

    if not ok:
        await message.reply_text(f"❌ Cannot install: {msg}")
        return

    await message.reply_text(
        f"⚙️ {msg}\nExtracting to staging and validating SQLite..."
    )

    try:
        extracted = await asyncio.to_thread(
            safe_extract_stream, ps, cfg.staging_dir
        )
        candidate, details = await asyncio.to_thread(
            find_sqlite_candidate, cfg.staging_dir, cfg.expected_table
        )

        if not candidate:
            await message.reply_text(
                f"❌ No healthy SQLite DB with table '{cfg.expected_table}' found.\n"
                f"Extracted files: {len(extracted)}"
            )
            return

        STATE_FILE.write_text(str(candidate), encoding="utf-8")

        await message.reply_text(
            "✅ Staging ready\n"
            f"DB: {candidate}\n"
            f"Size: {human_size(candidate.stat().st_size)}\n"
            f"quick_check: {details.get('quick_check')}\n"
            f"{cfg.expected_table} rows: {details.get('count')}\n\n"
            "Production has NOT been replaced yet.\n"
            "Use /activate CONFIRM when ready."
        )
    except Exception as e:
        logger.exception("Install failed")
        await message.reply_text(f"❌ Install failed: {type(e).__name__}: {e}")


@app.on_message(filters.command("staged"))
@admin_only
async def staged(client: Client, message: Message):
    if not STATE_FILE.exists():
        await message.reply_text("No staged database selected.")
        return

    p = Path(STATE_FILE.read_text().strip())

    if not p.exists():
        await message.reply_text(
            "Staged DB path exists in state but file is missing."
        )
        return

    st = await asyncio.to_thread(
        production_status, p, cfg.expected_table
    )

    await message.reply_text(
        f"Staged DB: {p}\n"
        f"Size: {human_size(st.get('size', 0))}\n"
        f"quick_check: {st.get('quick_check')}\n"
        f"rows: {st.get('count')}"
    )


@app.on_message(filters.command("dbstatus"))
@admin_only
async def dbstatus(client: Client, message: Message):
    st = await asyncio.to_thread(
        production_status, cfg.production_db, cfg.expected_table
    )

    if not st.get("exists"):
        await message.reply_text(
            f"❌ Production DB not found: {cfg.production_db}"
        )
        return

    await message.reply_text(
        f"Production DB: {cfg.production_db}\n"
        f"Size: {human_size(st.get('size', 0))}\n"
        f"quick_check: {st.get('quick_check')}\n"
        f"Has {cfg.expected_table}: {st.get('has_table')}\n"
        f"Rows: {st.get('count')}"
    )


async def restart_service(service: str):
    proc = await asyncio.create_subprocess_exec(
        "systemctl",
        "restart",
        service,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate()

    if proc.returncode != 0:
        raise RuntimeError(
            (err or out).decode(errors="replace").strip()
        )


@app.on_message(filters.command("activate"))
@admin_only
async def activate(client: Client, message: Message):
    args = args_of(message)

    if not args or args[0] != "CONFIRM":
        await message.reply_text("Use: /activate CONFIRM")
        return

    if not STATE_FILE.exists():
        await message.reply_text("❌ Nothing staged.")
        return

    staged_db = Path(STATE_FILE.read_text().strip())

    if not staged_db.exists():
        await message.reply_text("❌ Staged DB file missing.")
        return

    st = await asyncio.to_thread(
        production_status, staged_db, cfg.expected_table
    )

    if st.get("quick_check") != "ok" or not st.get("has_table"):
        await message.reply_text(
            "❌ Staged DB validation failed. Refusing activation."
        )
        return

    await message.reply_text(
        "⚙️ Backing up current DB and activating staged DB..."
    )

    try:
        backup = await asyncio.to_thread(
            activate_database,
            staged_db,
            cfg.production_db,
            cfg.backups_dir,
        )

        await restart_service(cfg.api_service)

        await message.reply_text(
            "✅ Database activated and API restarted.\n"
            f"Rows: {st.get('count')}\n"
            f"Backup: {backup if backup else 'No previous DB'}"
        )
    except Exception as e:
        logger.exception("Activation failed")
        await message.reply_text(
            f"❌ Activation failed: {type(e).__name__}: {e}"
        )


@app.on_message(filters.command("rollback"))
@admin_only
async def rollback(client: Client, message: Message):
    args = args_of(message)

    if len(args) < 2 or args[-1] != "CONFIRM":
        await message.reply_text(
            "Use: /rollback <backup_filename> CONFIRM"
        )
        return

    name = safe_filename(args[0])
    backup = cfg.backups_dir / name

    if not backup.exists():
        await message.reply_text("❌ Backup not found.")
        return

    st = await asyncio.to_thread(
        production_status, backup, cfg.expected_table
    )

    if st.get("quick_check") != "ok":
        await message.reply_text(
            "❌ Backup DB failed quick_check."
        )
        return

    try:
        await asyncio.to_thread(
            shutil.copy2, backup, cfg.production_db
        )
        await restart_service(cfg.api_service)
        await message.reply_text(
            "✅ Backup restored and API restarted."
        )
    except Exception as e:
        await message.reply_text(
            f"❌ Rollback failed: {type(e).__name__}: {e}"
        )


@app.on_message(filters.command("genkey"))
@admin_only
async def genkey(client: Client, message: Message):
    args = args_of(message)
    name = " ".join(args).strip()

    if not name:
        await message.reply_text("Usage: /genkey <name>")
        return

    key_id, raw = key_store.generate_key(
        cfg.keys_db, name, message.from_user.id
    )

    await message.reply_text(
        f"✅ API key generated\n"
        f"ID: {key_id}\n"
        f"Name: {name}\n\n"
        f"`{raw}`\n\n"
        "⚠️ Save it now. Raw key is not stored."
    )


@app.on_message(filters.command("keys"))
@admin_only
async def keys(client: Client, message: Message):
    rows = key_store.list_keys(cfg.keys_db)

    if not rows:
        await message.reply_text("No API keys.")
        return

    text = []

    for r in rows[:100]:
        text.append(
            f"{'🟢' if r['enabled'] else '🔴'} "
            f"#{r['id']} {r['name']} "
            f"{r['key_prefix']}… uses={r['use_count']}"
        )

    await message.reply_text("\n".join(text))


async def key_toggle(message: Message, enabled: bool):
    args = args_of(message)

    if not args:
        await message.reply_text("Missing key ID.")
        return

    try:
        kid = int(args[0])
    except ValueError:
        await message.reply_text("Invalid key ID.")
        return

    ok = key_store.set_enabled(cfg.keys_db, kid, enabled)
    await message.reply_text(
        "✅ Updated." if ok else "❌ Key not found."
    )


@app.on_message(filters.command("disable"))
@admin_only
async def disable(client: Client, message: Message):
    await key_toggle(message, False)


@app.on_message(filters.command("enable"))
@admin_only
async def enable(client: Client, message: Message):
    await key_toggle(message, True)


@app.on_message(filters.command("deletekey"))
@admin_only
async def deletekey(client: Client, message: Message):
    args = args_of(message)

    if len(args) < 2 or args[1] != "CONFIRM":
        await message.reply_text(
            "Use: /deletekey <id> CONFIRM"
        )
        return

    try:
        kid = int(args[0])
    except ValueError:
        await message.reply_text("Invalid key ID.")
        return

    ok = key_store.delete_key(cfg.keys_db, kid)

    await message.reply_text(
        "✅ Key deleted." if ok else "❌ Key not found."
    )


def main():
    logger.info(
        "Manager bot starting via Telegram MTProto (Pyrogram-compatible client)"
    )
    app.run()


if __name__ == "__main__":
    main()
