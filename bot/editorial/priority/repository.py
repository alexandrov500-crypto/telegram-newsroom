from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class EditorialPriorityRepository:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def record(
        self,
        *,
        pending_news_id: int,
        editorial_priority_score: float,
        urgency_class: str,
        factors: dict[str, float],
        warnings: list[str],
        momentum: dict[str, Any],
        balance: dict[str, Any],
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO editorial_priority_scores (
                    pending_news_id, editorial_priority_score, urgency_class,
                    factors_json, warnings_json, momentum_json, balance_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pending_news_id,
                    editorial_priority_score,
                    urgency_class,
                    json.dumps(factors),
                    json.dumps(warnings),
                    json.dumps(momentum),
                    json.dumps(balance),
                    _utcnow(),
                ),
            )
            conn.commit()

    def recent_scores(self, *, hours: int = 72, limit: int = 40) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT pending_news_id, editorial_priority_score, urgency_class,
                       factors_json, warnings_json, created_at
                FROM editorial_priority_scores
                WHERE created_at >= datetime('now', printf('-%d hours', ?))
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (hours, limit),
            ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            try:
                factors = json.loads(row["factors_json"] or "{}")
            except json.JSONDecodeError:
                factors = {}
            out.append(
                {
                    "pending_news_id": row["pending_news_id"],
                    "editorial_priority_score": row["editorial_priority_score"],
                    "urgency_class": row["urgency_class"],
                    "factors": factors,
                    "warnings": json.loads(row["warnings_json"] or "[]"),
                    "created_at": row["created_at"],
                    "topic_bucket": factors.get("topic_bucket"),
                },
            )
        return out

    def save_daily(self, day: str, snapshot: dict[str, Any]) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO editorial_priority_daily (date, snapshot_json, created_at)
                VALUES (?, ?, ?)
                ON CONFLICT(date) DO UPDATE SET
                    snapshot_json = excluded.snapshot_json,
                    created_at = excluded.created_at
                """,
                (day, json.dumps(snapshot), _utcnow()),
            )
            conn.commit()
