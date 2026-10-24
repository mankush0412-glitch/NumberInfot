from __future__ import annotations
import gzip
import io
import os
import re
import shutil
import sqlite3
import tarfile
from datetime import datetime, timezone
from pathlib import Path

PART_RE = re.compile(r"^(?P<stem>.+\.part\.)(?P<suffix>[a-z]{2,})$", re.I)

class MultiFileReader(io.RawIOBase):
    def __init__(self, paths: list[Path]):
        self.paths = paths
        self.index = 0
        self.fp = None
        self._open_next()

    def _open_next(self):
        if self.fp:
            self.fp.close()
            self.fp = None
        if self.index < len(self.paths):
            self.fp = self.paths[self.index].open("rb")
            self.index += 1

    def readable(self):
        return True

    def readinto(self, b):
        if self.fp is None:
            return 0
        view = memoryview(b)
        total = 0
        while total < len(view):
            chunk = self.fp.read(len(view) - total)
            if chunk:
                view[total:total+len(chunk)] = chunk
                total += len(chunk)
                if total:
                    return total
            else:
                self._open_next()
                if self.fp is None:
                    break
        return total

    def close(self):
        if self.fp:
            self.fp.close()
        super().close()

def _suffix_to_number(s: str) -> int:
    n = 0
    for c in s.lower():
        n = n * 26 + (ord(c) - 96)
    return n

def get_parts(uploads_dir: Path) -> list[Path]:
    parts = []
    for p in uploads_dir.iterdir() if uploads_dir.exists() else []:
        if p.is_file() and PART_RE.match(p.name):
            parts.append(p)
    return sorted(parts, key=lambda p: _suffix_to_number(PART_RE.match(p.name).group("suffix")))

def validate_part_sequence(parts: list[Path]):
    if not parts:
        return False, "No split parts found."
    matches = [PART_RE.match(p.name) for p in parts]
    stems = {m.group("stem") for m in matches}
    if len(stems) != 1:
        return False, "Parts have different base names."
    nums = [_suffix_to_number(m.group("suffix")) for m in matches]
    # Sequence can start from .aa; enforce that specifically for this split format.
    expected_start = _suffix_to_number("aa")
    if nums[0] != expected_start:
        return False, f"First part must be .aa, found {parts[0].name}"
    for prev, cur in zip(nums, nums[1:]):
        if cur != prev + 1:
            return False, "One or more middle parts are missing."
    return True, f"{len(parts)} contiguous parts found."

def safe_extract_stream(parts: list[Path], staging_dir: Path) -> list[Path]:
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True, exist_ok=True)

    raw = MultiFileReader(parts)
    buffered = io.BufferedReader(raw, buffer_size=1024 * 1024)
    gz = gzip.GzipFile(fileobj=buffered, mode="rb")

    extracted = []
    root = staging_dir.resolve()
    with tarfile.open(fileobj=gz, mode="r|") as tf:
        for member in tf:
            if not member.isfile():
                continue
            target = (staging_dir / member.name).resolve()
            if root not in target.parents and target != root:
                raise RuntimeError(f"Unsafe archive path: {member.name}")
            target.parent.mkdir(parents=True, exist_ok=True)
            src = tf.extractfile(member)
            if src is None:
                continue
            with target.open("wb") as dst:
                shutil.copyfileobj(src, dst, length=1024 * 1024)
            extracted.append(target)
    return extracted

def find_sqlite_candidate(staging_dir: Path, expected_table: str) -> tuple[Path | None, dict]:
    candidates = [p for p in staging_dir.rglob("*") if p.is_file()]
    diagnostics = {}
    for p in candidates:
        try:
            with p.open("rb") as f:
                if f.read(16) != b"SQLite format 3\x00":
                    continue
            conn = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
            try:
                quick = conn.execute("PRAGMA quick_check").fetchone()[0]
                table = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                    (expected_table,)
                ).fetchone()
                count = None
                if table:
                    count = conn.execute(f'SELECT COUNT(*) FROM "{expected_table}"').fetchone()[0]
                diagnostics[str(p)] = {"quick_check": quick, "table": bool(table), "count": count}
                if quick == "ok" and table:
                    return p, diagnostics[str(p)]
            finally:
                conn.close()
        except Exception as e:
            diagnostics[str(p)] = {"error": str(e)}
    return None, diagnostics

def production_status(db_path: Path, expected_table: str):
    if not db_path.exists():
        return {"exists": False}
    result = {"exists": True, "size": db_path.stat().st_size}
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            result["quick_check"] = conn.execute("PRAGMA quick_check").fetchone()[0]
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (expected_table,)
            ).fetchone()
            result["has_table"] = bool(row)
            if row:
                result["count"] = conn.execute(f'SELECT COUNT(*) FROM "{expected_table}"').fetchone()[0]
        finally:
            conn.close()
    except Exception as e:
        result["error"] = str(e)
    return result

def activate_database(staged_db: Path, production_db: Path, backups_dir: Path):
    if not staged_db.exists():
        raise RuntimeError("Staged database not found.")
    production_db.parent.mkdir(parents=True, exist_ok=True)
    backups_dir.mkdir(parents=True, exist_ok=True)

    backup = None
    if production_db.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup = backups_dir / f"{production_db.stem}_{stamp}{production_db.suffix}.bak"
        shutil.copy2(production_db, backup)

    temp = production_db.with_suffix(production_db.suffix + ".new")
    shutil.copy2(staged_db, temp)
    os.replace(temp, production_db)
    return backup
