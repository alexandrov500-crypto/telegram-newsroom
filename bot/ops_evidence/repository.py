from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class EvidenceReviewRepository:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def save_review(
        self,
        *,
        week_id: str,
        snapshot: dict[str, Any],
        confidence_band: str,
        confidence_score: float,
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO ops_evidence_reviews (
                    week_id, snapshot_json, confidence_band, confidence_score, created_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(week_id) DO UPDATE SET
                    snapshot_json = excluded.snapshot_json,
                    confidence_band = excluded.confidence_band,
                    confidence_score = excluded.confidence_score,
                    created_at = excluded.created_at
                """,
                (
                    week_id,
                    json.dumps(snapshot, default=str),
                    confidence_band,
                    confidence_score,
                    _utcnow(),
                ),
            )
            conn.commit()

    def load_review(self, week_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT snapshot_json FROM ops_evidence_reviews WHERE week_id = ?",
                (week_id,),
            ).fetchone()
        if not row:
            return None
        try:
            return json.loads(row["snapshot_json"] or "{}")
        except json.JSONDecodeError:
            return None

    def recent_reviews(self, *, limit: int = 8) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT week_id, confidence_band, confidence_score, created_at
                FROM ops_evidence_reviews
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]
