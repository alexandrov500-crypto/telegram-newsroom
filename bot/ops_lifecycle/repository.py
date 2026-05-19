from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class LifecycleRepository:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path, timeout=15)

    def record_run(self, run_type: str, summary: dict[str, Any], *, duration_ms: int) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO ops_lifecycle_runs (run_type, summary_json, duration_ms, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (run_type, json.dumps(summary, default=str), duration_ms, _utcnow()),
            )
            conn.commit()

    def recent_runs(self, *, limit: int = 10) -> list[dict[str, Any]]:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT run_type, summary_json, duration_ms, created_at
                FROM ops_lifecycle_runs ORDER BY created_at DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            try:
                summary = json.loads(row["summary_json"] or "{}")
            except json.JSONDecodeError:
                summary = {}
            out.append(
                {
                    "run_type": row["run_type"],
                    "summary": summary,
                    "duration_ms": row["duration_ms"],
                    "created_at": row["created_at"],
                },
            )
        return out

    def get_state(self) -> dict[str, Any]:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM ops_lifecycle_state WHERE id = 1").fetchone()
        if not row:
            return {}
        try:
            state = json.loads(row["state_json"] or "{}")
        except json.JSONDecodeError:
            state = {}
        return {
            "last_maintenance_at": row["last_maintenance_at"],
            "last_vacuum_at": row["last_vacuum_at"],
            "last_backup_at": row["last_backup_at"],
            "state": state,
            "updated_at": row["updated_at"],
        }

    def update_state(
        self,
        *,
        last_maintenance_at: str | None = None,
        last_vacuum_at: str | None = None,
        last_backup_at: str | None = None,
        state_patch: dict[str, Any] | None = None,
    ) -> None:
        current = self.get_state()
        state = dict(current.get("state") or {})
        if state_patch:
            state.update(state_patch)
        now = _utcnow()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO ops_lifecycle_state
                (id, last_maintenance_at, last_vacuum_at, last_backup_at, state_json, updated_at)
                VALUES (1, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    last_maintenance_at = COALESCE(excluded.last_maintenance_at, ops_lifecycle_state.last_maintenance_at),
                    last_vacuum_at = COALESCE(excluded.last_vacuum_at, ops_lifecycle_state.last_vacuum_at),
                    last_backup_at = COALESCE(excluded.last_backup_at, ops_lifecycle_state.last_backup_at),
                    state_json = excluded.state_json,
                    updated_at = excluded.updated_at
                """,
                (
                    last_maintenance_at or current.get("last_maintenance_at"),
                    last_vacuum_at or current.get("last_vacuum_at"),
                    last_backup_at or current.get("last_backup_at"),
                    json.dumps(state),
                    now,
                ),
            )
            conn.commit()

    def save_daily_summary(self, day: str, category: str, summary: dict[str, Any]) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO ops_lifecycle_daily (date, category, summary_json, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(date, category) DO UPDATE SET
                    summary_json = excluded.summary_json,
                    created_at = excluded.created_at
                """,
                (day, category, json.dumps(summary), _utcnow()),
            )
            conn.commit()
