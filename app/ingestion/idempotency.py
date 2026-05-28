"""Message-level idempotent ingestion (channel + message_id), survives restart."""

from __future__ import annotations

import hashlib
import logging
import sqlite3
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_DB_NAME = "ingestion_idempotency.db"
_store: IngestionIdempotencyStore | None = None
_lock = threading.RLock()


def message_fingerprint(channel: str, message_id: int) -> str:
    """Stable fingerprint: hash(channel + message_id) — no body churn on edit."""
    raw = f"{(channel or '').strip().lower()}|{int(message_id)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class IngestionIdempotencyStore:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path), timeout=5.0)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS processed_messages (
                    fingerprint TEXT PRIMARY KEY,
                    channel TEXT NOT NULL,
                    message_id INTEGER NOT NULL,
                    processed_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_processed_at ON processed_messages(processed_at)"
            )
            conn.commit()

    def try_claim(self, channel: str, message_id: int) -> bool:
        """
        Atomically claim message for processing.
        Returns True if this is the first time; False if already processed (DROP).
        """
        fp = message_fingerprint(channel, message_id)
        ch = (channel or "").strip().lower()
        mid = int(message_id)
        now = time.time()
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO processed_messages
                    (fingerprint, channel, message_id, processed_at)
                VALUES (?, ?, ?, ?)
                """,
                (fp, ch, mid, now),
            )
            conn.commit()
            return cur.rowcount == 1

    def is_processed(self, channel: str, message_id: int) -> bool:
        fp = message_fingerprint(channel, message_id)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM processed_messages WHERE fingerprint = ? LIMIT 1",
                (fp,),
            ).fetchone()
        return row is not None

    def count(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) FROM processed_messages").fetchone()
        return int(row[0]) if row else 0


def init_idempotency_store(runtime_dir: str) -> IngestionIdempotencyStore:
    global _store
    with _lock:
        path = Path(runtime_dir).expanduser().resolve() / _DB_NAME
        _store = IngestionIdempotencyStore(path)
        logger.info("ingestion idempotency store ready path=%s", path)
        return _store


def get_idempotency_store() -> IngestionIdempotencyStore | None:
    return _store


def reset_idempotency_store_for_tests() -> None:
    global _store
    with _lock:
        _store = None
