from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from bot.processing.entities import (
    ENTITY_TOPIC,
    ExtractionResult,
    ExtractedEntity,
    canonical_entity_key,
    normalize_entity_key,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EntityRecord:
    id: int
    entity_name: str
    entity_type: str
    mention_count: int
    recent_mentions: int = 0
    avg_priority: float = 0.0


@dataclass(frozen=True)
class EntityNewsItem:
    pending_news_id: int
    title: str
    link: str
    priority_score: float
    created_at: str


@dataclass(frozen=True)
class TopicStat:
    topic_name: str
    mention_count: int
    avg_priority: float


class EntityRepository:
    """SQLite entity graph and trending analytics."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _since_iso(self, hours: int) -> str:
        return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

    def upsert_entity(self, entity: ExtractedEntity) -> int | None:
        try:
            now = self._now()
            canonical = canonical_entity_key(entity.normalized_key or entity.display_name)
            with self._connect() as conn:
                row = conn.execute(
                    """
                    SELECT id, mention_count FROM entities
                    WHERE canonical_key = ? AND entity_type = ?
                    """,
                    (canonical, entity.entity_type),
                ).fetchone()
                if row is None:
                    row = conn.execute(
                        """
                        SELECT id, mention_count FROM entities
                        WHERE entity_name = ? AND entity_type = ?
                        """,
                        (entity.display_name, entity.entity_type),
                    ).fetchone()
                if row is not None:
                    entity_id = int(row["id"])
                    conn.execute(
                        """
                        UPDATE entities
                        SET mention_count = mention_count + 1,
                            updated_at = ?,
                            canonical_key = COALESCE(canonical_key, ?)
                        WHERE id = ?
                        """,
                        (now, canonical, entity_id),
                    )
                    conn.commit()
                    return entity_id

                cur = conn.execute(
                    """
                    INSERT INTO entities (
                        entity_name, entity_type, mention_count,
                        canonical_key, created_at, updated_at
                    ) VALUES (?, ?, 1, ?, ?, ?)
                    """,
                    (entity.display_name, entity.entity_type, canonical, now, now),
                )
                conn.commit()
                entity_id = int(cur.lastrowid)
                logger.info(
                    "event=entity_registered name=%r type=%s id=%d",
                    entity.display_name,
                    entity.entity_type,
                    entity_id,
                )
                return entity_id
        except sqlite3.IntegrityError:
            return self.upsert_entity(entity)
        except Exception:
            logger.exception(
                "event=entity_upsert_failed name=%r",
                entity.display_name,
            )
            return None

    def link_news_entity(
        self,
        *,
        entity_id: int,
        pending_news_id: int | None = None,
        cluster_id: int | None = None,
    ) -> None:
        try:
            with self._connect() as conn:
                exists = conn.execute(
                    """
                    SELECT 1 FROM news_entities
                    WHERE entity_id = ?
                      AND COALESCE(pending_news_id, -1) = COALESCE(?, -1)
                      AND COALESCE(cluster_id, -1) = COALESCE(?, -1)
                    LIMIT 1
                    """,
                    (entity_id, pending_news_id, cluster_id),
                ).fetchone()
                if exists:
                    return
                conn.execute(
                    """
                    INSERT INTO news_entities (
                        pending_news_id, cluster_id, entity_id, created_at
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (pending_news_id, cluster_id, entity_id, self._now()),
                )
                conn.commit()
        except Exception:
            logger.exception(
                "event=entity_link_failed entity_id=%s pending_news_id=%s",
                entity_id,
                pending_news_id,
            )

    async def index_news_item_async(
        self,
        *,
        title: str,
        summary: str | None,
        tags: list[str],
        pending_news_id: int | None = None,
        cluster_id: int | None = None,
        priority_score: float = 0.5,
    ) -> ExtractionResult:
        from bot.processing.entities import extract_entities

        try:
            result = await extract_entities(title, summary, tags)
            return self.index_extraction(
                result,
                pending_news_id=pending_news_id,
                cluster_id=cluster_id,
                priority_score=priority_score,
            )
        except Exception:
            logger.exception("event=entity_index_failed pending_news_id=%s", pending_news_id)
            return ExtractionResult()

    def index_extraction(
        self,
        result: ExtractionResult,
        *,
        pending_news_id: int | None = None,
        cluster_id: int | None = None,
        priority_score: float = 0.5,
    ) -> ExtractionResult:
        try:
            for topic in result.topics:
                topic_entity = ExtractedEntity(
                    display_name=topic,
                    entity_type=ENTITY_TOPIC,
                    normalized_key=normalize_entity_key(topic),
                )
                entity_id = self.upsert_entity(topic_entity)
                if entity_id is not None:
                    self.link_news_entity(
                        entity_id=entity_id,
                        pending_news_id=pending_news_id,
                        cluster_id=cluster_id,
                    )

            for entity in result.entities:
                entity_id = self.upsert_entity(entity)
                if entity_id is None:
                    continue
                self.link_news_entity(
                    entity_id=entity_id,
                    pending_news_id=pending_news_id,
                    cluster_id=cluster_id,
                )
                if priority_score >= 0.85:
                    logger.info(
                        "event=trending_entity_detected name=%r score=%.2f",
                        entity.display_name,
                        priority_score,
                    )
            return result
        except Exception:
            logger.exception("event=entity_index_failed")
            return result

    def get_trending_entities(self, *, limit: int = 10, hours: int = 48) -> list[EntityRecord]:
        since = self._since_iso(hours)
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT
                        e.id,
                        e.entity_name,
                        e.entity_type,
                        e.mention_count,
                        COUNT(ne.id) AS recent_mentions,
                        AVG(COALESCE(p.priority_score, 0.5)) AS avg_priority
                    FROM entities e
                    LEFT JOIN news_entities ne
                        ON ne.entity_id = e.id AND ne.created_at >= ?
                    LEFT JOIN pending_news p ON p.id = ne.pending_news_id
                    WHERE e.entity_type != ?
                    GROUP BY e.id
                    ORDER BY recent_mentions DESC, e.mention_count DESC
                    LIMIT ?
                    """,
                    (since, ENTITY_TOPIC, limit),
                ).fetchall()
            return [
                EntityRecord(
                    id=int(row["id"]),
                    entity_name=str(row["entity_name"]),
                    entity_type=str(row["entity_type"]),
                    mention_count=int(row["mention_count"] or 0),
                    recent_mentions=int(row["recent_mentions"] or 0),
                    avg_priority=float(row["avg_priority"] or 0.5),
                )
                for row in rows
                if int(row["recent_mentions"] or 0) > 0 or int(row["mention_count"] or 0) > 0
            ]
        except Exception:
            logger.exception("event=trending_entities_failed")
            return []

    def get_entity_names_for_pending(
        self,
        pending_news_id: int,
        *,
        limit: int = 6,
    ) -> list[str]:
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT e.entity_name
                    FROM news_entities ne
                    JOIN entities e ON e.id = ne.entity_id
                    WHERE ne.pending_news_id = ?
                    ORDER BY e.mention_count DESC, e.entity_name ASC
                    LIMIT ?
                    """,
                    (pending_news_id, limit),
                ).fetchall()
            return [str(row["entity_name"]) for row in rows]
        except Exception:
            logger.exception(
                "event=entity_names_failed pending_news_id=%s",
                pending_news_id,
            )
            return []

    def get_entity_news(self, name_query: str, *, limit: int = 10) -> tuple[EntityRecord | None, list[EntityNewsItem]]:
        key = normalize_entity_key(name_query)
        try:
            with self._connect() as conn:
                entity_row = conn.execute(
                    """
                    SELECT id, entity_name, entity_type, mention_count
                    FROM entities
                    WHERE lower(entity_name) = lower(?)
                       OR lower(entity_name) LIKE ?
                    ORDER BY mention_count DESC
                    LIMIT 1
                    """,
                    (name_query, f"%{name_query}%"),
                ).fetchone()
                if entity_row is None:
                    return None, []

                entity = EntityRecord(
                    id=int(entity_row["id"]),
                    entity_name=str(entity_row["entity_name"]),
                    entity_type=str(entity_row["entity_type"]),
                    mention_count=int(entity_row["mention_count"] or 0),
                )
                news_rows = conn.execute(
                    """
                    SELECT p.id, p.title, p.link, p.priority_score, p.created_at
                    FROM news_entities ne
                    JOIN pending_news p ON p.id = ne.pending_news_id
                    WHERE ne.entity_id = ?
                    ORDER BY p.priority_score DESC, p.created_at DESC
                    LIMIT ?
                    """,
                    (entity.id, limit),
                ).fetchall()
            items = [
                EntityNewsItem(
                    pending_news_id=int(row["id"]),
                    title=str(row["title"]),
                    link=str(row["link"]),
                    priority_score=float(row["priority_score"] or 0.5),
                    created_at=str(row["created_at"]),
                )
                for row in news_rows
            ]
            return entity, items
        except Exception:
            logger.exception("event=entity_news_failed query=%r", name_query)
            return None, []

    def get_top_topics(self, *, limit: int = 10, hours: int = 168) -> list[TopicStat]:
        since = self._since_iso(hours)
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT
                        e.entity_name AS topic_name,
                        COUNT(ne.id) AS mention_count,
                        AVG(COALESCE(p.priority_score, 0.5)) AS avg_priority
                    FROM entities e
                    JOIN news_entities ne ON ne.entity_id = e.id
                    LEFT JOIN pending_news p ON p.id = ne.pending_news_id
                    WHERE e.entity_type = ?
                      AND ne.created_at >= ?
                    GROUP BY e.id
                    ORDER BY mention_count DESC, avg_priority DESC
                    LIMIT ?
                    """,
                    (ENTITY_TOPIC, since, limit),
                ).fetchall()
            return [
                TopicStat(
                    topic_name=str(row["topic_name"]),
                    mention_count=int(row["mention_count"] or 0),
                    avg_priority=float(row["avg_priority"] or 0.5),
                )
                for row in rows
            ]
        except Exception:
            logger.exception("event=top_topics_failed")
            return []

    def trending_display_names(self, *, limit: int = 5) -> list[str]:
        return [entity.entity_name for entity in self.get_trending_entities(limit=limit)[:limit]]
