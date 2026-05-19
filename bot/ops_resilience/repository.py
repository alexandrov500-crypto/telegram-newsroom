from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class ResilienceRepository:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def save_state(
        self,
        *,
        posture: str,
        posture_reason: str,
        dependencies: dict[str, Any],
        budgets: dict[str, Any],
        backpressure: dict[str, Any],
        guidance: list[dict[str, Any]],
        forecast: dict[str, Any],
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO ops_resilience_state (
                    id, posture, posture_reason, dependencies_json, budgets_json,
                    backpressure_json, guidance_json, forecast_json, updated_at
                ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    posture = excluded.posture,
                    posture_reason = excluded.posture_reason,
                    dependencies_json = excluded.dependencies_json,
                    budgets_json = excluded.budgets_json,
                    backpressure_json = excluded.backpressure_json,
                    guidance_json = excluded.guidance_json,
                    forecast_json = excluded.forecast_json,
                    updated_at = excluded.updated_at
                """,
                (
                    posture,
                    posture_reason,
                    json.dumps(dependencies),
                    json.dumps(budgets),
                    json.dumps(backpressure),
                    json.dumps(guidance),
                    json.dumps(forecast),
                    _utcnow(),
                ),
            )
            conn.commit()

    def load_state(self) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM ops_resilience_state WHERE id = 1").fetchone()
        if not row:
            return None
        return {
            "posture": row["posture"],
            "posture_reason": row["posture_reason"],
            "dependencies": _json(row["dependencies_json"]),
            "budgets": _json(row["budgets_json"]),
            "backpressure": _json(row["backpressure_json"]),
            "guidance": _json(row["guidance_json"]),
            "forecast": _json(row["forecast_json"]),
            "updated_at": row["updated_at"],
        }

    def record_event(
        self,
        event_type: str,
        *,
        subsystem: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO ops_resilience_events (event_type, subsystem, detail_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (event_type, subsystem, json.dumps(detail or {}), _utcnow()),
            )
            conn.commit()

    def record_recovery(
        self,
        *,
        subsystem: str,
        outcome: str,
        duration_sec: float | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO ops_resilience_recovery_log (
                    subsystem, outcome, duration_sec, detail_json, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (subsystem, outcome, duration_sec, json.dumps(detail or {}), _utcnow()),
            )
            conn.commit()

    def events_since(self, *, hours: int = 168, event_type: str | None = None) -> list[dict[str, Any]]:
        with self._conn() as conn:
            if event_type:
                rows = conn.execute(
                    """
                    SELECT * FROM ops_resilience_events
                    WHERE created_at >= datetime('now', printf('-%d hours', ?))
                      AND event_type = ?
                    ORDER BY created_at DESC
                    """,
                    (hours, event_type),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM ops_resilience_events
                    WHERE created_at >= datetime('now', printf('-%d hours', ?))
                    ORDER BY created_at DESC
                    """,
                    (hours,),
                ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            out.append(
                {
                    "event_type": row["event_type"],
                    "subsystem": row["subsystem"],
                    "detail": _json(row["detail_json"]),
                    "created_at": row["created_at"],
                },
            )
        return out

    def recovery_log_since(self, *, hours: int = 168) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT subsystem, outcome, duration_sec, detail_json, created_at
                FROM ops_resilience_recovery_log
                WHERE created_at >= datetime('now', printf('-%d hours', ?))
                ORDER BY created_at DESC
                """,
                (hours,),
            ).fetchall()
        return [
            {
                "subsystem": r["subsystem"],
                "outcome": r["outcome"],
                "duration_sec": r["duration_sec"],
                "detail": _json(r["detail_json"]),
                "created_at": r["created_at"],
            }
            for r in rows
        ]

    def save_daily(self, day: str, snapshot: dict[str, Any]) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO ops_resilience_daily (date, snapshot_json, created_at)
                VALUES (?, ?, ?)
                ON CONFLICT(date) DO UPDATE SET
                    snapshot_json = excluded.snapshot_json,
                    created_at = excluded.created_at
                """,
                (day, json.dumps(snapshot), _utcnow()),
            )
            conn.commit()


def _json(raw: str | None) -> Any:
    try:
        return json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
