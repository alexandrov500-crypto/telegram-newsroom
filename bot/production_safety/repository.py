from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ProductionSafetyRepository:
    """Persistence for forensics, audit, rollout, poison queue."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def save_forensics_trace(
        self,
        *,
        trace_id: str,
        story_id: int | None,
        trace_type: str,
        payload: dict[str, Any],
        correlation_id: str | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO ops_forensics_traces
                (trace_id, story_id, trace_type, payload_json, correlation_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    trace_id,
                    story_id,
                    trace_type,
                    json.dumps(payload, default=str),
                    correlation_id,
                    self._now(),
                ),
            )
            conn.commit()

    def get_story_traces(self, story_id: int, *, limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM ops_forensics_traces
                WHERE story_id = ? ORDER BY created_at DESC LIMIT ?
                """,
                (story_id, limit),
            ).fetchall()
        out: list[dict[str, Any]] = []
        for r in rows:
            d = dict(r)
            try:
                d["payload"] = json.loads(d.pop("payload_json", "{}"))
            except json.JSONDecodeError:
                d["payload"] = {}
            out.append(d)
        return out

    def audit_command(
        self,
        *,
        operator_id: str,
        command: str,
        args_preview: str = "",
        success: bool = True,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO ops_admin_audit
                (operator_id, command, args_preview, success, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (operator_id, command, args_preview[:500], 1 if success else 0, self._now()),
            )
            conn.commit()

    def operator_heartbeat(self, operator_id: str, *, command: str | None = None) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO ops_operator_heartbeat
                (operator_id, last_seen_at, last_command)
                VALUES (?, ?, ?)
                """,
                (operator_id, self._now(), command),
            )
            conn.commit()

    def list_operator_heartbeats(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM ops_operator_heartbeat ORDER BY last_seen_at DESC",
            ).fetchall()
        return [dict(r) for r in rows]

    def get_rollout_stage(self) -> str:
        with self._connect() as conn:
            row = conn.execute("SELECT stage FROM ops_rollout_state WHERE id = 1").fetchone()
        if row is None:
            return "INTERNAL_SHADOW"
        return str(row["stage"])

    def set_rollout_stage(
        self,
        stage: str,
        *,
        previous: str | None = None,
        detail: dict[str, Any] | None = None,
        increment_rollback: bool = False,
    ) -> None:
        with self._connect() as conn:
            row = conn.execute("SELECT rollback_count FROM ops_rollout_state WHERE id = 1").fetchone()
            rb = int(row["rollback_count"]) if row else 0
            if increment_rollback:
                rb += 1
            conn.execute(
                """
                INSERT OR REPLACE INTO ops_rollout_state
                (id, stage, previous_stage, rollback_count, updated_at, detail_json)
                VALUES (1, ?, ?, ?, ?, ?)
                """,
                (
                    stage,
                    previous,
                    rb,
                    self._now(),
                    json.dumps(detail or {}, default=str),
                ),
            )
            conn.commit()

    def quarantine_poison(
        self,
        *,
        message_key: str,
        subsystem: str,
        reason: str,
        payload_preview: str = "",
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO ops_poison_queue
                (message_key, subsystem, payload_preview, reason, quarantined_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (message_key, subsystem, payload_preview[:300], reason, self._now()),
            )
            conn.commit()

    def poison_count(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS c FROM ops_poison_queue").fetchone()
        return int(row["c"]) if row else 0
