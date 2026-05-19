from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class TrustCalibrationRepository:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def record_event(
        self,
        *,
        subsystem: str,
        signal_type: str,
        signal_value: str | None = None,
        operator_action: str | None = None,
        outcome: str | None = None,
        pending_news_id: int | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO ops_trust_calibration_events (
                    pending_news_id, subsystem, signal_type, signal_value,
                    operator_action, outcome, detail_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pending_news_id,
                    subsystem,
                    signal_type,
                    signal_value,
                    operator_action,
                    outcome,
                    json.dumps(detail or {}),
                    _utcnow(),
                ),
            )
            conn.commit()

    def events_since(self, *, hours: int = 168, subsystem: str | None = None) -> list[dict[str, Any]]:
        with self._conn() as conn:
            if subsystem:
                rows = conn.execute(
                    """
                    SELECT * FROM ops_trust_calibration_events
                    WHERE created_at >= datetime('now', printf('-%d hours', ?))
                      AND subsystem = ?
                    ORDER BY created_at DESC
                    """,
                    (hours, subsystem),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM ops_trust_calibration_events
                    WHERE created_at >= datetime('now', printf('-%d hours', ?))
                    ORDER BY created_at DESC
                    """,
                    (hours,),
                ).fetchall()
        return [dict(r) for r in rows]

    def save_subsystem_daily(
        self,
        day: str,
        subsystem: str,
        metrics: dict[str, Any],
        trust_band: str,
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO ops_trust_subsystem_daily (date, subsystem, metrics_json, trust_band, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(date, subsystem) DO UPDATE SET
                    metrics_json = excluded.metrics_json,
                    trust_band = excluded.trust_band,
                    created_at = excluded.created_at
                """,
                (day, subsystem, json.dumps(metrics), trust_band, _utcnow()),
            )
            conn.commit()

    def save_calibration_daily(self, day: str, snapshot: dict[str, Any]) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO ops_trust_calibration_daily (date, snapshot_json, created_at)
                VALUES (?, ?, ?)
                ON CONFLICT(date) DO UPDATE SET
                    snapshot_json = excluded.snapshot_json,
                    created_at = excluded.created_at
                """,
                (day, json.dumps(snapshot), _utcnow()),
            )
            conn.commit()

    def load_subsystem_daily(self, *, days: int = 14) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT date, subsystem, metrics_json, trust_band
                FROM ops_trust_subsystem_daily
                WHERE date >= date('now', printf('-%d days', ?))
                ORDER BY date DESC, subsystem
                """,
                (days,),
            ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            try:
                metrics = json.loads(row["metrics_json"] or "{}")
            except json.JSONDecodeError:
                metrics = {}
            out.append(
                {
                    "date": row["date"],
                    "subsystem": row["subsystem"],
                    "trust_band": row["trust_band"],
                    "metrics": metrics,
                },
            )
        return out

    def ratings_with_traces(self, *, limit: int = 200) -> list[dict[str, Any]]:
        """Join post ratings with publish traces for agreement analysis."""
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT r.pending_news_id, r.rating, r.created_at AS rated_at,
                       t.trace_json
                FROM live_channel_post_ratings r
                LEFT JOIN live_publish_trace t ON t.post_id = CAST(r.pending_news_id AS TEXT)
                ORDER BY r.created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            trace: dict[str, Any] = {}
            try:
                trace = json.loads(row["trace_json"] or "{}")
            except (json.JSONDecodeError, TypeError):
                pass
            out.append(
                {
                    "pending_news_id": row["pending_news_id"],
                    "rating": row["rating"],
                    "rated_at": row["rated_at"],
                    "trace": trace,
                },
            )
        return out
