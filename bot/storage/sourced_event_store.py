from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bot.events.envelope import EventEnvelope
from bot.events.validation import validate_envelope

logger = logging.getLogger(__name__)


class SourcedEventStore:
    """Append-only immutable event log with monotonic sequence IDs."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        return conn

    def next_sequence(self) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(sequence_id), 0) + 1 AS n FROM sourced_event_log",
            ).fetchone()
            return int(row["n"])

    def append(self, envelope: EventEnvelope, *, status: str = "pending") -> int:
        validate_envelope(envelope)
        seq = self.next_sequence()
        monotonic_id = f"{envelope.node_id}:{seq:012d}"
        signed = envelope.to_dict(sign=True)
        if not signed.get("event_id"):
            signed["event_id"] = monotonic_id
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO sourced_event_log (
                    sequence_id, event_id, event_type, envelope_json, partition_key,
                    correlation_id, causation_id, node_id, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    seq,
                    signed["event_id"],
                    signed["event_type"],
                    json.dumps(signed),
                    signed.get("partition_key", "global"),
                    signed.get("correlation_id"),
                    signed.get("causation_id"),
                    signed.get("node_id"),
                    status,
                    signed.get("timestamp", datetime.now(timezone.utc).isoformat()),
                ),
            )
            conn.commit()
        return seq

    def get_by_sequence(self, sequence_id: int) -> EventEnvelope | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT envelope_json FROM sourced_event_log WHERE sequence_id = ?",
                (sequence_id,),
            ).fetchone()
        if row is None:
            return None
        return EventEnvelope.from_dict(json.loads(row["envelope_json"]), verify_signature=False)

    def replay_range(
        self,
        *,
        from_sequence: int = 1,
        limit: int = 100,
        event_type: str | None = None,
    ) -> list[EventEnvelope]:
        with self._connect() as conn:
            if event_type:
                rows = conn.execute(
                    """
                    SELECT envelope_json FROM sourced_event_log
                    WHERE sequence_id >= ? AND event_type = ?
                    ORDER BY sequence_id ASC
                    LIMIT ?
                    """,
                    (from_sequence, event_type, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT envelope_json FROM sourced_event_log
                    WHERE sequence_id >= ?
                    ORDER BY sequence_id ASC
                    LIMIT ?
                    """,
                    (from_sequence, limit),
                ).fetchall()
        out: list[EventEnvelope] = []
        for row in rows:
            try:
                out.append(
                    EventEnvelope.from_dict(
                        json.loads(row["envelope_json"]),
                        verify_signature=False,
                    ),
                )
            except Exception:
                logger.exception("event=sourced_replay_parse_failed")
        return out

    def mark_processed(self, event_id: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE sourced_event_log
                SET status = 'processed', processed_at = ?
                WHERE event_id = ?
                """,
                (now, event_id),
            )
            conn.commit()

    def quarantine(self, event_id: str, *, reason: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE sourced_event_log
                SET status = 'quarantined', processed_at = ?, quarantine_reason = ?
                WHERE event_id = ?
                """,
                (now, reason[:500], event_id),
            )
            conn.commit()

    def timeline(
        self,
        *,
        correlation_id: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT sequence_id, event_id, event_type, status, created_at, node_id
                FROM sourced_event_log
                WHERE correlation_id = ?
                ORDER BY sequence_id ASC
                LIMIT ?
                """,
                (correlation_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def count_by_status(self, status: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM sourced_event_log WHERE status = ?",
                (status,),
            ).fetchone()
        return int(row["c"]) if row else 0
