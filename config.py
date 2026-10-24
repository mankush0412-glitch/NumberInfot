import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    bot_token: str
    admin_ids: set[int]
    api_id: int
    api_hash: str
    uploads_dir: Path
    staging_dir: Path
    production_db: Path
    backups_dir: Path
    keys_db: Path
    api_service: str
    expected_table: str


def load_config() -> Config:
    token = os.getenv("BOT_TOKEN", "").strip()
    admins_raw = os.getenv("ADMIN_IDS", "").strip()
    admins = {int(x.strip()) for x in admins_raw.split(",") if x.strip()}

    if not token:
        raise RuntimeError("BOT_TOKEN missing in .env")

    if not admins:
        raise RuntimeError("ADMIN_IDS missing in .env")

    api_id_raw = os.getenv("TELEGRAM_API_ID", "").strip()
    api_hash = os.getenv("TELEGRAM_API_HASH", "").strip()

    try:
        api_id = int(api_id_raw) if api_id_raw else 0
    except ValueError:
        raise RuntimeError("TELEGRAM_API_ID must be a number")

    return Config(
        bot_token=token,
        admin_ids=admins,
        api_id=api_id,
        api_hash=api_hash,
        uploads_dir=Path(os.getenv("UPLOADS_DIR", "/opt/users-api/uploads")),
        staging_dir=Path(os.getenv("STAGING_DIR", "/opt/users-api/staging")),
        production_db=Path(os.getenv("DB_PATH", "/opt/users-api/hitek2.db")),
        backups_dir=Path(os.getenv("BACKUPS_DIR", "/opt/users-api/backups")),
        keys_db=Path(os.getenv("KEYS_DB_PATH", "/opt/users-api/api_keys.db")),
        api_service=os.getenv("API_SERVICE", "users-api"),
        expected_table=os.getenv("EXPECTED_TABLE", "users"),
    )
