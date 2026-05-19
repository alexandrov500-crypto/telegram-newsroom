from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


class TelegramSeenRepository:
    """Tracks ingested Telegram channel messages."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path, timeout=5.0)

    def is_seen(self, channel: str, message_id: int) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT 1 FROM telegram_seen_messages
                WHERE channel = ? AND message_id = ?
                LIMIT 1
                """,
                (channel, message_id),
            ).fetchone()
        return row is not None

    def mark_seen(self, channel: str, message_id: int) -> None:
        seen_at = datetime.now(timezone.utc).isoformat()
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO telegram_seen_messages (
                        channel, message_id, seen_at
                    ) VALUES (?, ?, ?)
                    """,
                    (channel, message_id, seen_at),
                )
                conn.commit()
        except sqlite3.Error:
            logger.exception(
                "event=telegram_seen_write_failed channel=%r message_id=%d",
                channel,
                message_id,
            )
