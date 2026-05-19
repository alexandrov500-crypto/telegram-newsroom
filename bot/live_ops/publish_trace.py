from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class PublishTraceStore:
    """Persistent publish decision trace for operator debugging."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path, timeout=10)

    def record_decision(
        self,
        *,
        pending_news_id: int,
        mode: str,
        channel: str | int | None,
        source: str,
        cluster_id: int | None,
        confidence_score: float,
        trust_score: float,
        safety_score: float,
        guard_result: str,
        hold_reason: str | None,
        operator_override: bool,
        published: bool,
        blockers: list[str] | None = None,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        post_id = str(pending_news_id)
        if correlation_id is None:
            try:
                from bot.ops_forensics.correlation import get_correlation_id

                correlation_id = get_correlation_id()
            except Exception:
                pass
        trace = {
            "post_id": post_id,
            "correlation_id": correlation_id,
            "timestamp": _utcnow(),
            "mode": mode,
            "channel": str(channel) if channel is not None else None,
            "source": source,
            "cluster_id": cluster_id,
            "confidence_score": confidence_score,
            "trust_score": trust_score,
            "safety_score": safety_score,
            "guard_result": guard_result,
            "hold_reason": hold_reason,
            "operator_override": operator_override,
            "published": published,
            "blockers": blockers or [],
        }
        now = _utcnow()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO live_publish_trace (post_id, pending_news_id, trace_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(post_id) DO UPDATE SET
                    trace_json = excluded.trace_json,
                    updated_at = excluded.updated_at
                """,
                (post_id, pending_news_id, json.dumps(trace), now, now),
            )
            conn.commit()
        return trace

    def merge_fields(self, pending_news_id: int, fields: dict[str, Any]) -> None:
        """Merge advisory fields into trace_json (e.g. editorial_quality). Never raises."""
        post_id = str(pending_news_id)
        row = self.get(pending_news_id)
        if not row:
            return
        trace = dict(row)
        trace.update(fields)
        trace["timestamp"] = _utcnow()
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE live_publish_trace SET trace_json = ?, updated_at = ? WHERE post_id = ?
                """,
                (json.dumps(trace), _utcnow(), post_id),
            )
            conn.commit()

    def update_published(self, pending_news_id: int, *, published: bool, guard_result: str) -> None:
        post_id = str(pending_news_id)
        row = self.get(pending_news_id)
        if not row:
            return
        trace = dict(row)
        trace["published"] = published
        trace["guard_result"] = guard_result
        trace["timestamp"] = _utcnow()
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE live_publish_trace SET trace_json = ?, updated_at = ? WHERE post_id = ?
                """,
                (json.dumps(trace), _utcnow(), post_id),
            )
            conn.commit()

    def get(self, pending_news_id: int) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT trace_json FROM live_publish_trace WHERE post_id = ?",
                (str(pending_news_id),),
            ).fetchone()
        return json.loads(row[0]) if row else None

    def recent(self, *, limit: int = 20) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT trace_json FROM live_publish_trace
                ORDER BY updated_at DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [json.loads(r[0]) for r in rows]
