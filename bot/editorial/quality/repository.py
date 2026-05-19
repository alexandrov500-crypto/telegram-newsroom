from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class EditorialQualityRepository:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def record_score(
        self,
        *,
        pending_news_id: int,
        editorial_quality_score: float,
        dimensions: dict[str, float],
        warnings: list[str],
        fatigue: dict[str, float],
        drift: dict[str, float],
        headline: str,
        summary: str,
        source: str | None,
        template_key: str,
        tags: list[str],
    ) -> None:
        now = _utcnow()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO editorial_quality_scores (
                    pending_news_id, editorial_quality_score, dimensions_json,
                    warnings_json, fatigue_json, drift_json,
                    headline, summary, source, template_key, tags_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pending_news_id,
                    editorial_quality_score,
                    json.dumps(dimensions),
                    json.dumps(warnings),
                    json.dumps(fatigue),
                    json.dumps(drift),
                    headline[:500],
                    (summary or "")[:2000],
                    source,
                    template_key,
                    json.dumps(tags),
                    now,
                ),
            )
            for phrase in warnings:
                if not phrase.startswith(("repetitive phrasing", "weak phrasing")):
                    continue
                part = phrase.split(":", 1)[-1].strip().lower()
                if len(part) < 4:
                    continue
                conn.execute(
                    """
                    INSERT INTO editorial_phrase_stats (phrase, count_7d, last_seen_at)
                    VALUES (?, 1, ?)
                    ON CONFLICT(phrase) DO UPDATE SET
                        count_7d = count_7d + 1,
                        last_seen_at = excluded.last_seen_at
                    """,
                    (part, now),
                )
            conn.commit()

    def recent_posts(self, *, limit: int = 20, hours: int = 72) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT pending_news_id, headline, summary, source, template_key,
                       tags_json, dimensions_json, editorial_quality_score, created_at
                FROM editorial_quality_scores
                WHERE created_at >= datetime('now', printf('-%d hours', ?))
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (hours, limit),
            ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            dims: dict[str, Any] = {}
            try:
                dims = json.loads(row["dimensions_json"] or "{}")
            except json.JSONDecodeError:
                pass
            tags: list[str] = []
            try:
                tags = json.loads(row["tags_json"] or "[]")
            except json.JSONDecodeError:
                pass
            out.append(
                {
                    "pending_news_id": row["pending_news_id"],
                    "headline": row["headline"],
                    "summary": row["summary"],
                    "source": row["source"],
                    "template_key": row["template_key"],
                    "tags": tags,
                    "editorial_quality_score": row["editorial_quality_score"],
                    "information_density": dims.get("information_density"),
                    "verbosity": dims.get("readability"),
                    "weak_phrase_count": 0,
                    "hashtag_count": dims.get("hashtag_quality"),
                    "created_at": row["created_at"],
                },
            )
        return out

    def recent_for_compare(
        self,
        *,
        exclude_pending_news_id: int | None,
        limit: int = 15,
    ) -> list[dict[str, Any]]:
        rows = self.recent_posts(limit=limit + 5)
        if exclude_pending_news_id is None:
            return rows[:limit]
        return [r for r in rows if r["pending_news_id"] != exclude_pending_news_id][:limit]

    def top_phrases(self, *, limit: int = 15) -> list[tuple[str, int]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT phrase, count_7d FROM editorial_phrase_stats
                ORDER BY count_7d DESC, last_seen_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [(str(r["phrase"]), int(r["count_7d"])) for r in rows]

    def scores_since(self, *, hours: int = 24) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT pending_news_id, editorial_quality_score, headline, source,
                       template_key, warnings_json, dimensions_json, created_at
                FROM editorial_quality_scores
                WHERE created_at >= datetime('now', printf('-%d hours', ?))
                ORDER BY editorial_quality_score ASC, created_at DESC
                """,
                (hours,),
            ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            warnings: list[str] = []
            dims: dict[str, Any] = {}
            try:
                warnings = json.loads(row["warnings_json"] or "[]")
            except json.JSONDecodeError:
                pass
            try:
                dims = json.loads(row["dimensions_json"] or "{}")
            except json.JSONDecodeError:
                pass
            result.append(
                {
                    "pending_news_id": row["pending_news_id"],
                    "editorial_quality_score": row["editorial_quality_score"],
                    "headline": row["headline"],
                    "source": row["source"],
                    "template_key": row["template_key"],
                    "warnings": warnings,
                    "dimensions": dims,
                    "created_at": row["created_at"],
                },
            )
        return result

    def save_daily_snapshot(self, day: str, snapshot: dict[str, Any]) -> None:
        now = _utcnow()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO editorial_quality_daily (date, snapshot_json, created_at)
                VALUES (?, ?, ?)
                ON CONFLICT(date) DO UPDATE SET
                    snapshot_json = excluded.snapshot_json,
                    created_at = excluded.created_at
                """,
                (day, json.dumps(snapshot), now),
            )
            conn.commit()

    def load_daily_snapshots(self, *, limit: int = 14) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT date, snapshot_json FROM editorial_quality_daily
                ORDER BY date DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            try:
                snap = json.loads(row["snapshot_json"] or "{}")
            except json.JSONDecodeError:
                snap = {}
            snap["date"] = row["date"]
            out.append(snap)
        return out

    def prune_phrase_stats_older_than_days(self, days: int = 7) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE editorial_phrase_stats
                SET count_7d = 0
                WHERE last_seen_at < datetime('now', printf('-%d days', ?))
                """,
                (days,),
            )
            conn.commit()
