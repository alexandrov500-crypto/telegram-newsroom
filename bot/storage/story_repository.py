from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from bot.editorial.story_types import StorySnapshot, StoryStatus
from bot.processing.semantic import build_fingerprint, tokens_to_storage

logger = logging.getLogger(__name__)

_ACTIVE_STATUSES = (
    StoryStatus.CREATED.value,
    StoryStatus.ACTIVE.value,
    StoryStatus.TRENDING.value,
    StoryStatus.COOLDOWN.value,
)


@dataclass(frozen=True)
class StoryTimelineEntry:
    created_at: str
    headline: str
    summary: str | None
    event_type: str
    significance: float


@dataclass(frozen=True)
class StoryEventRecord:
    id: int
    story_id: int
    event_type: str
    significance: float
    headline: str
    summary: str | None
    pending_news_id: int | None
    cluster_id: int | None
    created_at: str


class StoryRepository:
    """SQLite persistence for editorial story memory."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _row_to_snapshot(self, row: sqlite3.Row, *, entities: tuple[str, ...] = ()) -> StorySnapshot:
        tags_raw = row["geopolitical_tags"]
        tags: tuple[str, ...] = ()
        if tags_raw:
            try:
                parsed = json.loads(tags_raw)
                if isinstance(parsed, list):
                    tags = tuple(str(t) for t in parsed)
            except json.JSONDecodeError:
                tags = ()

        return StorySnapshot(
            id=int(row["id"]),
            title=str(row["title"]),
            canonical_summary=row["canonical_summary"],
            status=str(row["status"]),
            importance_score=float(row["importance_score"] or 0.5),
            novelty_score=float(row["novelty_score"] or 0.5),
            trend_velocity=float(row["trend_velocity"] or 0.0),
            geopolitical_tags=tags,
            languages_json=row["languages_json"],
            fingerprint_storage=row["fingerprint_storage"],
            first_seen_at=str(row["first_seen_at"]),
            last_updated_at=str(row["last_updated_at"]),
            cluster_count=int(row["cluster_count"] or 0),
            source_count=int(row["source_count"] or 0),
            entity_names=entities,
        )

    def create_story(
        self,
        *,
        title: str,
        canonical_summary: str | None,
        status: str = StoryStatus.CREATED.value,
        geopolitical_tags: list[str] | None = None,
        languages: list[str] | None = None,
        importance_score: float = 0.5,
        novelty_score: float = 0.5,
        trend_velocity: float = 0.0,
        cluster_count: int = 1,
        source_count: int = 1,
        canonical_cluster_id: int | None = None,
    ) -> int:
        now = self._now()
        tokens, _ = build_fingerprint(title)
        fingerprint = tokens_to_storage(tokens)
        tags_json = json.dumps(geopolitical_tags or [])
        langs_json = json.dumps(sorted(set(languages or [])))

        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO stories (
                    title, canonical_summary, status, fingerprint_storage,
                    geopolitical_tags, languages_json, first_seen_at, last_updated_at,
                    importance_score, novelty_score, trend_velocity,
                    cluster_count, source_count, canonical_cluster_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    title,
                    canonical_summary,
                    status,
                    fingerprint,
                    tags_json,
                    langs_json,
                    now,
                    now,
                    importance_score,
                    novelty_score,
                    trend_velocity,
                    cluster_count,
                    source_count,
                    canonical_cluster_id,
                ),
            )
            story_id = int(cur.lastrowid)
            conn.execute(
                """
                INSERT INTO story_metrics (
                    story_id, importance_score, novelty_score, trend_velocity,
                    redundancy_score, update_delta_score, metrics_json, updated_at
                ) VALUES (?, ?, ?, ?, 0, 0, '{}', ?)
                """,
                (story_id, importance_score, novelty_score, trend_velocity, now),
            )
            conn.commit()
        return story_id

    def update_story(
        self,
        story_id: int,
        *,
        title: str | None = None,
        canonical_summary: str | None = None,
        status: str | None = None,
        importance_score: float | None = None,
        novelty_score: float | None = None,
        trend_velocity: float | None = None,
        cluster_count: int | None = None,
        source_count: int | None = None,
        geopolitical_tags: list[str] | None = None,
        languages: list[str] | None = None,
        refresh_fingerprint: bool = False,
    ) -> None:
        fields: list[str] = ["last_updated_at = ?"]
        values: list[object] = [self._now()]

        if title is not None:
            fields.append("title = ?")
            values.append(title)
            if refresh_fingerprint:
                tokens, _ = build_fingerprint(title)
                fields.append("fingerprint_storage = ?")
                values.append(tokens_to_storage(tokens))
        if canonical_summary is not None:
            fields.append("canonical_summary = ?")
            values.append(canonical_summary)
        if status is not None:
            fields.append("status = ?")
            values.append(status)
        if importance_score is not None:
            fields.append("importance_score = ?")
            values.append(importance_score)
        if novelty_score is not None:
            fields.append("novelty_score = ?")
            values.append(novelty_score)
        if trend_velocity is not None:
            fields.append("trend_velocity = ?")
            values.append(trend_velocity)
        if cluster_count is not None:
            fields.append("cluster_count = ?")
            values.append(cluster_count)
        if source_count is not None:
            fields.append("source_count = ?")
            values.append(source_count)
        if geopolitical_tags is not None:
            fields.append("geopolitical_tags = ?")
            values.append(json.dumps(geopolitical_tags))
        if languages is not None:
            fields.append("languages_json = ?")
            values.append(json.dumps(sorted(set(languages))))

        values.append(story_id)
        with self._connect() as conn:
            conn.execute(
                f"UPDATE stories SET {', '.join(fields)} WHERE id = ?",
                values,
            )
            conn.commit()

    def get_story(self, story_id: int) -> StorySnapshot | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM stories WHERE id = ?",
                (story_id,),
            ).fetchone()
            if row is None:
                return None
            entities = self._entity_names_for_story(conn, story_id)
        return self._row_to_snapshot(row, entities=entities)

    def story_id_for_cluster(self, cluster_id: int) -> int | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT story_id FROM story_cluster_links WHERE cluster_id = ?",
                (cluster_id,),
            ).fetchone()
        return int(row["story_id"]) if row else None

    def link_cluster(
        self,
        *,
        story_id: int,
        cluster_id: int,
        pending_news_id: int | None = None,
    ) -> None:
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO story_cluster_links (story_id, cluster_id, pending_news_id, linked_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(cluster_id) DO UPDATE SET
                    story_id = excluded.story_id,
                    pending_news_id = COALESCE(excluded.pending_news_id, pending_news_id),
                    linked_at = excluded.linked_at
                """,
                (story_id, cluster_id, pending_news_id, now),
            )
            if pending_news_id is not None:
                conn.execute(
                    "UPDATE pending_news SET story_id = ? WHERE id = ?",
                    (story_id, pending_news_id),
                )
            conn.commit()

    def add_event(
        self,
        *,
        story_id: int,
        event_type: str,
        significance: float,
        headline: str,
        summary: str | None = None,
        pending_news_id: int | None = None,
        cluster_id: int | None = None,
    ) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO story_events (
                    story_id, event_type, significance, headline, summary,
                    pending_news_id, cluster_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    story_id,
                    event_type,
                    significance,
                    headline,
                    summary,
                    pending_news_id,
                    cluster_id,
                    self._now(),
                ),
            )
            conn.commit()
            return int(cur.lastrowid)

    def upsert_entities(self, story_id: int, entity_names: list[str]) -> None:
        if not entity_names:
            return
        with self._connect() as conn:
            for name in entity_names:
                clean = name.strip()
                if not clean:
                    continue
                conn.execute(
                    """
                    INSERT INTO story_entities (story_id, entity_name, mention_count)
                    VALUES (?, ?, 1)
                    ON CONFLICT(story_id, entity_name) DO UPDATE SET
                        mention_count = mention_count + 1
                    """,
                    (story_id, clean[:120]),
                )
            conn.commit()

    def entity_map_for_stories(self, story_ids: list[int]) -> dict[int, set[str]]:
        if not story_ids:
            return {}
        placeholders = ",".join("?" * len(story_ids))
        result: dict[int, set[str]] = {sid: set() for sid in story_ids}
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT story_id, entity_name FROM story_entities
                WHERE story_id IN ({placeholders})
                """,
                story_ids,
            ).fetchall()
        for row in rows:
            result[int(row["story_id"])].add(str(row["entity_name"]))
        return result

    def _entity_names_for_story(
        self,
        conn: sqlite3.Connection,
        story_id: int,
    ) -> tuple[str, ...]:
        rows = conn.execute(
            """
            SELECT entity_name FROM story_entities
            WHERE story_id = ?
            ORDER BY mention_count DESC, entity_name ASC
            LIMIT 24
            """,
            (story_id,),
        ).fetchall()
        return tuple(str(row["entity_name"]) for row in rows)

    def update_metrics(
        self,
        story_id: int,
        *,
        importance_score: float,
        novelty_score: float,
        trend_velocity: float,
        redundancy_score: float,
        update_delta_score: float,
        metrics_json: dict | None = None,
    ) -> None:
        now = self._now()
        payload = json.dumps(metrics_json or {})
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO story_metrics (
                    story_id, importance_score, novelty_score, trend_velocity,
                    redundancy_score, update_delta_score, metrics_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(story_id) DO UPDATE SET
                    importance_score = excluded.importance_score,
                    novelty_score = excluded.novelty_score,
                    trend_velocity = excluded.trend_velocity,
                    redundancy_score = excluded.redundancy_score,
                    update_delta_score = excluded.update_delta_score,
                    metrics_json = excluded.metrics_json,
                    updated_at = excluded.updated_at
                """,
                (
                    story_id,
                    importance_score,
                    novelty_score,
                    trend_velocity,
                    redundancy_score,
                    update_delta_score,
                    payload,
                    now,
                ),
            )
            conn.commit()

    def list_active_stories(
        self,
        *,
        limit: int = 80,
        max_age_days: int = 14,
    ) -> list[StorySnapshot]:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=max_age_days)).isoformat()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM stories
                WHERE status IN (?, ?, ?, ?)
                  AND last_updated_at >= ?
                ORDER BY importance_score DESC, last_updated_at DESC
                LIMIT ?
                """,
                (*_ACTIVE_STATUSES, cutoff, limit),
            ).fetchall()
            ids = [int(row["id"]) for row in rows]
            entity_map = self._entity_map(conn, ids)

        return [
            self._row_to_snapshot(
                row,
                entities=tuple(entity_map.get(int(row["id"]), set())),
            )
            for row in rows
        ]

    def _entity_map(
        self,
        conn: sqlite3.Connection,
        story_ids: list[int],
    ) -> dict[int, set[str]]:
        if not story_ids:
            return {}
        placeholders = ",".join("?" * len(story_ids))
        rows = conn.execute(
            f"""
            SELECT story_id, entity_name FROM story_entities
            WHERE story_id IN ({placeholders})
            """,
            story_ids,
        ).fetchall()
        out: dict[int, set[str]] = {}
        for row in rows:
            sid = int(row["story_id"])
            out.setdefault(sid, set()).add(str(row["entity_name"]))
        return out

    def list_trending(self, *, limit: int = 10) -> list[StorySnapshot]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM stories
                WHERE status IN (?, ?)
                ORDER BY trend_velocity DESC, importance_score DESC
                LIMIT ?
                """,
                (StoryStatus.TRENDING.value, StoryStatus.ACTIVE.value, limit),
            ).fetchall()
            ids = [int(row["id"]) for row in rows]
            entity_map = self._entity_map(conn, ids)
        return [
            self._row_to_snapshot(row, entities=tuple(entity_map.get(int(row["id"]), set())))
            for row in rows
        ]

    def list_top_by_importance(self, *, limit: int = 10) -> list[StorySnapshot]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM stories
                WHERE status != ?
                ORDER BY importance_score DESC, last_updated_at DESC
                LIMIT ?
                """,
                (StoryStatus.ARCHIVED.value, limit),
            ).fetchall()
            ids = [int(row["id"]) for row in rows]
            entity_map = self._entity_map(conn, ids)
        return [
            self._row_to_snapshot(row, entities=tuple(entity_map.get(int(row["id"]), set())))
            for row in rows
        ]

    def timeline(self, story_id: int, *, limit: int = 12) -> list[StoryTimelineEntry]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT created_at, headline, summary, event_type, significance
                FROM story_events
                WHERE story_id = ?
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (story_id, limit),
            ).fetchall()
        return [
            StoryTimelineEntry(
                created_at=str(row["created_at"]),
                headline=str(row["headline"]),
                summary=row["summary"],
                event_type=str(row["event_type"]),
                significance=float(row["significance"]),
            )
            for row in rows
        ]

    def recent_events(self, story_id: int, *, limit: int = 5) -> list[StoryEventRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, story_id, event_type, significance, headline, summary,
                       pending_news_id, cluster_id, created_at
                FROM story_events
                WHERE story_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (story_id, limit),
            ).fetchall()
        return [
            StoryEventRecord(
                id=int(row["id"]),
                story_id=int(row["story_id"]),
                event_type=str(row["event_type"]),
                significance=float(row["significance"]),
                headline=str(row["headline"]),
                summary=row["summary"],
                pending_news_id=row["pending_news_id"],
                cluster_id=row["cluster_id"],
                created_at=str(row["created_at"]),
            )
            for row in rows
        ]

    def upsert_relationship(
        self,
        *,
        left_entity: str,
        right_entity: str,
        weight_delta: float = 1.0,
        story_id: int | None = None,
    ) -> None:
        left, right = sorted((left_entity.lower(), right_entity.lower()))
        if left == right:
            return
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO story_relationships (
                    left_entity, right_entity, weight, story_id, updated_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(left_entity, right_entity, story_id) DO UPDATE SET
                    weight = weight + excluded.weight,
                    updated_at = excluded.updated_at
                """,
                (left, right, weight_delta, story_id, now),
            )
            conn.commit()

    def count_by_status(self) -> dict[str, int]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT status, COUNT(*) AS cnt FROM stories GROUP BY status"
            ).fetchall()
        return {str(row["status"]): int(row["cnt"]) for row in rows}

    def archive_stale_stories(self, *, inactive_hours: int = 168) -> int:
        cutoff = (
            datetime.now(timezone.utc) - timedelta(hours=inactive_hours)
        ).isoformat()
        with self._connect() as conn:
            cur = conn.execute(
                """
                UPDATE stories
                SET status = ?
                WHERE status IN (?, ?, ?)
                  AND last_updated_at < ?
                """,
                (
                    StoryStatus.ARCHIVED.value,
                    StoryStatus.ACTIVE.value,
                    StoryStatus.TRENDING.value,
                    StoryStatus.COOLDOWN.value,
                    cutoff,
                ),
            )
            conn.commit()
            return int(cur.rowcount)

    def count_active(self) -> int:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS cnt FROM stories
                WHERE status IN (?, ?, ?, ?)
                """,
                _ACTIVE_STATUSES,
            ).fetchone()
        return int(row["cnt"]) if row else 0
