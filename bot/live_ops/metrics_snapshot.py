from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class LiveMetricsSnapshotter:
    """Periodic operational metrics timeline (default every 5 minutes)."""

    def __init__(self, db_path: Path, *, interval_sec: float = 300.0) -> None:
        self._db_path = db_path
        self.interval_sec = interval_sec
        self._last_snapshot = 0.0

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path, timeout=10)

    def maybe_snapshot(self, metrics: dict[str, Any]) -> dict[str, Any] | None:
        now = time.monotonic()
        if now - self._last_snapshot < self.interval_sec:
            return None
        self._last_snapshot = now
        return self.save(metrics)

    def save(self, metrics: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "published_last_hour": metrics.get("published_last_hour", 0),
            "held_last_hour": metrics.get("held_last_hour", 0),
            "rollback_count": metrics.get("rollback_count", 0),
            "freeze_count": metrics.get("freeze_count", 0),
            "engagement_score": metrics.get("engagement_score", 0.0),
            "fatigue_score": metrics.get("fatigue_score", 0.0),
            "incident_rate": metrics.get("incident_rate", 0.0),
            "channel_health": metrics.get("channel_health", 0.0),
            "timestamp": _utcnow(),
        }
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO live_metrics_snapshots (snapshot_json, created_at)
                VALUES (?, ?)
                """,
                (json.dumps(payload), _utcnow()),
            )
            conn.commit()
        return payload

    def latest(self) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT snapshot_json FROM live_metrics_snapshots ORDER BY id DESC LIMIT 1",
            ).fetchone()
        return json.loads(row[0]) if row else None

    def timeline(self, *, limit: int = 48) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT snapshot_json FROM live_metrics_snapshots
                ORDER BY id DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [json.loads(r[0]) for r in reversed(rows)]
