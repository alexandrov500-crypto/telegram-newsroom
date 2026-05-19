from __future__ import annotations

import gzip
import json
import logging
import os
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from bot.config import project_root

logger = logging.getLogger(__name__)


def archive_root() -> Path:
    raw = Path(os.getenv("OPS_ARCHIVE_ROOT", "var/archives"))
    if not raw.is_absolute():
        return project_root() / raw
    return raw


def ensure_archive_dirs() -> Path:
    root = archive_root()
    for sub in ("backups", "pulses", "bundles", "exports"):
        (root / sub).mkdir(parents=True, exist_ok=True)
    return root


def gzip_copy_file(src: Path, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with src.open("rb") as fin, gzip.open(dest, "wb") as fout:
        shutil.copyfileobj(fin, fout)
    return dest


def backup_database(db_path: Path) -> Path | None:
    """SQLite file backup to cold storage. Never raises."""
    import os

    if not db_path.is_file():
        return None
    root = ensure_archive_dirs()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    dest = root / "backups" / f"newsroom_{stamp}.db.gz"
    try:
        gzip_copy_file(db_path, dest)
        return dest
    except Exception:
        logger.debug("event=lifecycle_backup_failed path=%s", db_path)
        return None


def verify_sqlite_integrity(db_path: Path) -> bool:
    try:
        with sqlite3.connect(db_path, timeout=5) as conn:
            row = conn.execute("PRAGMA quick_check").fetchone()
        return row is not None and row[0] == "ok"
    except Exception:
        return False


def archive_file(path: Path, *, category: str) -> Path | None:
    if not path.is_file():
        return None
    root = ensure_archive_dirs()
    day = datetime.now(timezone.utc).date().isoformat()
    dest = root / category / day / path.name
    if dest.suffix not in (".gz",):
        dest = dest.with_suffix(dest.suffix + ".gz")
    try:
        gzip_copy_file(path, dest)
        return dest
    except Exception:
        return None


def write_export_bundle(db_path: Path, payload: dict) -> Path:
    root = ensure_archive_dirs()
    day = datetime.now(timezone.utc).date().isoformat()
    out = root / "exports" / f"lifecycle_{day}.json.gz"
    out.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(payload, indent=2, default=str).encode("utf-8")
    with gzip.open(out, "wb") as fh:
        fh.write(raw)
    return out
