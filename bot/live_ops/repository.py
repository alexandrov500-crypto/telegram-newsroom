from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class LiveChannelRepository:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path, timeout=10)

    def ensure_state(self, *, live_mode: str = "shadow") -> dict[str, Any]:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO live_channel_state
                (id, live_mode, paused, frozen, publishes_this_hour, failures_recent,
                 trust_score, content_stability_score, detail_json, updated_at)
                VALUES (1, ?, 0, 0, 0, 0, 0.85, 0.9, '{}', ?)
                """,
                (live_mode, _utcnow()),
            )
            conn.commit()
        return self.get_state() or {}

    def get_state(self) -> dict[str, Any] | None:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM live_channel_state WHERE id = 1").fetchone()
        return dict(row) if row else None

    def update_state(self, **fields: Any) -> None:
        self.ensure_state()
        allowed = {
            "live_mode",
            "paused",
            "frozen",
            "publishes_this_hour",
            "hour_bucket",
            "failures_recent",
            "cooldown_until",
            "last_rollback_at",
            "trust_score",
            "content_stability_score",
            "detail_json",
        }
        parts = []
        vals: list[Any] = []
        for k, v in fields.items():
            if k not in allowed:
                continue
            parts.append(f"{k} = ?")
            vals.append(json.dumps(v) if k == "detail_json" and isinstance(v, dict) else v)
        if not parts:
            return
        parts.append("updated_at = ?")
        vals.append(_utcnow())
        with self._conn() as conn:
            conn.execute(
                f"UPDATE live_channel_state SET {', '.join(parts)} WHERE id = 1",
                vals,
            )
            conn.commit()

    def log_publish(
        self,
        *,
        pending_news_id: int,
        channel_id: int | None,
        live_mode: str,
        action: str,
        passed: bool,
        blockers: list[str] | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO live_channel_publish_log
                (pending_news_id, channel_id, live_mode, action, passed, blockers_json,
                 detail_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pending_news_id,
                    channel_id,
                    live_mode,
                    action,
                    1 if passed else 0,
                    json.dumps(blockers or []),
                    json.dumps(detail or {}),
                    _utcnow(),
                ),
            )
            conn.commit()

    def recent_publishes(self, *, limit: int = 20) -> list[dict[str, Any]]:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT * FROM live_channel_publish_log
                ORDER BY created_at DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def record_feedback(self, metric: str, value: float, *, pending_news_id: int | None = None, detail: dict | None = None) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO live_channel_feedback
                (pending_news_id, metric, value, detail_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (pending_news_id, metric, value, json.dumps(detail or {}), _utcnow()),
            )
            conn.commit()

    def rate_post(
        self,
        *,
        pending_news_id: int,
        rating: str,
        operator_id: int | None = None,
        note: str = "",
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO live_channel_post_ratings
                (pending_news_id, rating, operator_id, note, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (pending_news_id, rating, operator_id, note, _utcnow()),
            )
            conn.commit()

    def record_incident(self, incident_type: str, severity: str, detail: dict[str, Any]) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO live_channel_incidents
                (incident_type, severity, detail_json, resolved, created_at)
                VALUES (?, ?, ?, 0, ?)
                """,
                (incident_type, severity, json.dumps(detail), _utcnow()),
            )
            conn.commit()

    def recent_incidents(self, *, limit: int = 15) -> list[dict[str, Any]]:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT * FROM live_channel_incidents
                ORDER BY created_at DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def publish_success_rate(self, *, window: int = 50) -> float:
        rows = self.recent_publishes(limit=window)
        if not rows:
            return 1.0
        passed = sum(1 for r in rows if r.get("passed"))
        return passed / len(rows)

    def rollback_count_24h(self) -> int:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) FROM live_channel_publish_log
                WHERE action = 'rollback_batch' AND created_at > datetime('now', '-1 day')
                """,
            ).fetchone()
        return int(row[0] if row else 0)
