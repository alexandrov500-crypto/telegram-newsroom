from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class GoLiveRepository:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path, timeout=10)

    def get_state(self) -> dict[str, Any] | None:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM go_live_state WHERE id = 1").fetchone()
        return dict(row) if row else None

    def set_state(
        self,
        *,
        publication_stage: str,
        rollout_stage: str,
        operator_signoff: str | None = None,
        snapshot: dict[str, Any] | None = None,
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO go_live_state
                (id, publication_stage, rollout_stage, operator_signoff, snapshot_json, updated_at)
                VALUES (1, ?, ?, ?, ?, ?)
                """,
                (
                    publication_stage,
                    rollout_stage,
                    operator_signoff,
                    json.dumps(snapshot or {}),
                    _utcnow(),
                ),
            )
            conn.commit()
