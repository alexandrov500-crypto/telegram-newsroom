from __future__ import annotations

import hashlib
import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_DEDUP_WINDOW_HOURS = 72


@dataclass(frozen=True, slots=True)
class PublishReceipt:
    idempotency_key: str
    pending_news_id: int | None
    telegram_message_id: int | None
    status: str
    created_at: str


class PublishIdempotencyStore:
    """Transactional publish deduplication — exactly-once-ish Telegram delivery."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def build_key(
        *,
        pending_news_id: int | None = None,
        digest_id: int | None = None,
        channel_id: int | None = None,
        language: str = "en",
        content_hash: str | None = None,
    ) -> str:
        parts = [
            str(pending_news_id or ""),
            str(digest_id or ""),
            str(channel_id or ""),
            language,
            content_hash or "",
        ]
        digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
        return f"pub:{digest[:32]}"

    def try_begin(
        self,
        idempotency_key: str,
        *,
        pending_news_id: int | None,
        digest_id: int | None,
        channel_id: int | None,
        language: str,
        node_id: str,
    ) -> PublishReceipt | None:
        """
        Reserve publish slot. Returns existing receipt if duplicate within window.
        Returns None if new reservation acquired.
        """
        now = self._now()
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=_DEDUP_WINDOW_HOURS)).isoformat()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT idempotency_key, pending_news_id, telegram_message_id, status, created_at
                FROM publish_receipts
                WHERE idempotency_key = ? AND created_at >= ?
                """,
                (idempotency_key, cutoff),
            ).fetchone()
            if row is not None:
                return PublishReceipt(
                    idempotency_key=str(row["idempotency_key"]),
                    pending_news_id=row["pending_news_id"],
                    telegram_message_id=row["telegram_message_id"],
                    status=str(row["status"]),
                    created_at=str(row["created_at"]),
                )
            try:
                conn.execute(
                    """
                    INSERT INTO publish_receipts (
                        idempotency_key, pending_news_id, digest_id, channel_id,
                        language, telegram_message_id, node_id, status, created_at
                    ) VALUES (?, ?, ?, ?, ?, NULL, ?, 'in_progress', ?)
                    """,
                    (
                        idempotency_key,
                        pending_news_id,
                        digest_id,
                        channel_id,
                        language,
                        node_id,
                        now,
                    ),
                )
                conn.commit()
                return None
            except sqlite3.IntegrityError:
                row = conn.execute(
                    "SELECT * FROM publish_receipts WHERE idempotency_key = ?",
                    (idempotency_key,),
                ).fetchone()
                if row is None:
                    return None
                return PublishReceipt(
                    idempotency_key=str(row["idempotency_key"]),
                    pending_news_id=row["pending_news_id"],
                    telegram_message_id=row["telegram_message_id"],
                    status=str(row["status"]),
                    created_at=str(row["created_at"]),
                )

    def complete(
        self,
        idempotency_key: str,
        *,
        telegram_message_id: int,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE publish_receipts
                SET status = 'completed', telegram_message_id = ?
                WHERE idempotency_key = ?
                """,
                (telegram_message_id, idempotency_key),
            )
            conn.commit()

    def fail(self, idempotency_key: str, *, allow_retry: bool = True) -> None:
        status = "failed" if allow_retry else "aborted"
        with self._connect() as conn:
            conn.execute(
                "UPDATE publish_receipts SET status = ? WHERE idempotency_key = ?",
                (status, idempotency_key),
            )
            conn.commit()

    def get_receipt(self, idempotency_key: str) -> PublishReceipt | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT idempotency_key, pending_news_id, telegram_message_id, status, created_at
                FROM publish_receipts WHERE idempotency_key = ?
                """,
                (idempotency_key,),
            ).fetchone()
        if row is None:
            return None
        return PublishReceipt(
            idempotency_key=str(row["idempotency_key"]),
            pending_news_id=row["pending_news_id"],
            telegram_message_id=row["telegram_message_id"],
            status=str(row["status"]),
            created_at=str(row["created_at"]),
        )
