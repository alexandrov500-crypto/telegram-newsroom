from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path

from bot.events.types import NewsroomEvent

logger = logging.getLogger(__name__)


class EventStore:
    """SQLite-backed event log for replay and observability."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        return conn

    def append(self, event: NewsroomEvent) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO newsroom_event_log (
                    event_id, event_type, payload_json, status, created_at
                ) VALUES (?, ?, ?, 'pending', ?)
                """,
                (
                    event.event_id,
                    event.event_type,
                    json.dumps(event.payload),
                    event.created_at,
                ),
            )
            conn.commit()

    def mark_processed(self, event_id: str) -> None:
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE newsroom_event_log
                SET status = 'processed', processed_at = ?
                WHERE event_id = ?
                """,
                (now, event_id),
            )
            conn.commit()

    def recent_unprocessed(self, *, limit: int = 100) -> list[NewsroomEvent]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT event_id, event_type, payload_json, created_at
                FROM newsroom_event_log
                WHERE status = 'pending'
                ORDER BY id ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        events: list[NewsroomEvent] = []
        for row in rows:
            try:
                payload = json.loads(row["payload_json"])
            except json.JSONDecodeError:
                payload = {}
            events.append(
                NewsroomEvent(
                    event_id=str(row["event_id"]),
                    event_type=str(row["event_type"]),
                    created_at=str(row["created_at"]),
                    payload=payload,
                ),
            )
        return events

    def move_to_dead_letter(self, event_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE newsroom_event_log
                SET status = 'dead_letter'
                WHERE event_id = ?
                """,
                (event_id,),
            )
            conn.commit()
