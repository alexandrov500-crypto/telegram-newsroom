from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class ConsolidationRepository:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def save_snapshot(self, day: str, snapshot: dict[str, Any], complexity_score: float) -> None:
        with sqlite3.connect(self._db_path, timeout=10) as conn:
            conn.execute(
                """
                INSERT INTO ops_consolidation_snapshots (date, snapshot_json, complexity_score, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(date) DO UPDATE SET
                    snapshot_json = excluded.snapshot_json,
                    complexity_score = excluded.complexity_score,
                    created_at = excluded.created_at
                """,
                (day, json.dumps(snapshot, default=str), complexity_score, _utcnow()),
            )
            conn.commit()

    def load_latest(self) -> dict[str, Any] | None:
        with sqlite3.connect(self._db_path, timeout=10) as conn:
            row = conn.execute(
                """
                SELECT snapshot_json, complexity_score, date FROM ops_consolidation_snapshots
                ORDER BY date DESC LIMIT 1
                """,
            ).fetchone()
        if not row:
            return None
        try:
            snap = json.loads(row[0] or "{}")
        except json.JSONDecodeError:
            snap = {}
        snap["_complexity_score"] = row[1]
        snap["_date"] = row[2]
        return snap
