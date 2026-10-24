import hashlib
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

def _connect(db_path: Path):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn

def init_db(db_path: Path):
    with _connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS api_keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                key_hash TEXT NOT NULL UNIQUE,
                key_prefix TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                created_by INTEGER,
                last_used_at TEXT,
                use_count INTEGER NOT NULL DEFAULT 0
            )
        """)
        conn.commit()

def hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()

def generate_key(db_path: Path, name: str, created_by: int):
    raw = secrets.token_urlsafe(48)
    now = datetime.now(timezone.utc).isoformat()
    with _connect(db_path) as conn:
        cur = conn.execute("""
            INSERT INTO api_keys(name,key_hash,key_prefix,enabled,created_at,created_by)
            VALUES(?,?,?,?,?,?)
        """, (name, hash_key(raw), raw[:10], 1, now, created_by))
        conn.commit()
    return cur.lastrowid, raw

def list_keys(db_path: Path):
    with _connect(db_path) as conn:
        return [dict(r) for r in conn.execute("""
            SELECT id,name,key_prefix,enabled,created_at,last_used_at,use_count
            FROM api_keys ORDER BY id DESC
        """).fetchall()]

def set_enabled(db_path: Path, key_id: int, enabled: bool) -> bool:
    with _connect(db_path) as conn:
        cur = conn.execute("UPDATE api_keys SET enabled=? WHERE id=?", (1 if enabled else 0, key_id))
        conn.commit()
        return cur.rowcount > 0

def delete_key(db_path: Path, key_id: int) -> bool:
    with _connect(db_path) as conn:
        cur = conn.execute("DELETE FROM api_keys WHERE id=?", (key_id,))
        conn.commit()
        return cur.rowcount > 0

def validate_key(db_path: Path, raw: str) -> bool:
    now = datetime.now(timezone.utc).isoformat()
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT id FROM api_keys WHERE key_hash=? AND enabled=1",
            (hash_key(raw),)
        ).fetchone()
        if not row:
            return False
        conn.execute(
            "UPDATE api_keys SET last_used_at=?, use_count=use_count+1 WHERE id=?",
            (now, row["id"])
        )
        conn.commit()
        return True
