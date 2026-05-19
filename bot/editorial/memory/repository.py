from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bot.editorial.memory.topics import (
    extract_entity_keys,
    extract_topic_keys,
    primary_storyline_slug,
    storyline_id_from_slug,
)
from bot.editorial.memory.types import StoryEventRecord, StorylineSnapshot


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class EditorialMemoryRepository:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _row_to_storyline(row: sqlite3.Row) -> StorylineSnapshot:
        try:
            topics = json.loads(row["topic_keys_json"] or "[]")
        except json.JSONDecodeError:
            topics = []
        try:
            entities = json.loads(row["entity_keys_json"] or "[]")
        except json.JSONDecodeError:
            entities = []
        try:
            sources = json.loads(row["source_diversity_json"] or "[]")
        except json.JSONDecodeError:
            sources = []
        return StorylineSnapshot(
            storyline_id=row["storyline_id"],
            slug=row["slug"],
            title=row["title"],
            topic_keys=tuple(topics),
            entity_keys=tuple(entities),
            first_seen_at=row["first_seen_at"],
            last_updated_at=row["last_updated_at"],
            publish_count=int(row["publish_count"]),
            sources=tuple(sources),
            latest_headline=row["latest_headline"],
            latest_summary=row["latest_summary"],
            tone_direction=row["tone_direction"],
            saturation_score=float(row["saturation_score"] or 0),
            cluster_id=row["cluster_id"],
        )

    def recent_posts(self, *, limit: int = 20, hours: int = 72) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT pending_news_id, headline, summary, source, tags_json, created_at
                FROM editorial_story_events
                WHERE created_at >= datetime('now', printf('-%d hours', ?))
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (hours, limit),
            ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            try:
                tags = json.loads(row["tags_json"] or "[]")
            except json.JSONDecodeError:
                tags = []
            out.append(
                {
                    "pending_news_id": row["pending_news_id"],
                    "headline": row["headline"],
                    "summary": row["summary"],
                    "source": row["source"],
                    "tags": tags,
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
        rows = self.recent_posts(limit=limit + 5, hours=72)
        if exclude_pending_news_id is None:
            return rows[:limit]
        return [r for r in rows if r.get("pending_news_id") != exclude_pending_news_id][:limit]

    def active_storylines(self, *, days: int = 30, limit: int = 40) -> list[StorylineSnapshot]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM editorial_storylines
                WHERE last_updated_at >= datetime('now', printf('-%d days', ?))
                ORDER BY last_updated_at DESC
                LIMIT ?
                """,
                (days, limit),
            ).fetchall()
        return [self._row_to_storyline(r) for r in rows]

    def get_storyline(self, storyline_id: str) -> StorylineSnapshot | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM editorial_storylines WHERE storyline_id = ?",
                (storyline_id,),
            ).fetchone()
        return self._row_to_storyline(row) if row else None

    def publish_count_72h(self, storyline_id: str) -> int:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS c FROM editorial_story_events
                WHERE storyline_id = ? AND created_at >= datetime('now', '-72 hours')
                """,
                (storyline_id,),
            ).fetchone()
        return int(row["c"]) if row else 0

    def events_for_storyline(self, storyline_id: str, *, limit: int = 30) -> list[StoryEventRecord]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM editorial_story_events
                WHERE storyline_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (storyline_id, limit),
            ).fetchall()
        out: list[StoryEventRecord] = []
        for row in rows:
            try:
                flags = json.loads(row["contradiction_flags_json"] or "[]")
            except json.JSONDecodeError:
                flags = []
            out.append(
                StoryEventRecord(
                    id=int(row["id"]),
                    storyline_id=row["storyline_id"],
                    pending_news_id=row["pending_news_id"],
                    event_type=row["event_type"],
                    follow_up_kind=row["follow_up_kind"],
                    headline=row["headline"],
                    summary=row["summary"],
                    source=row["source"],
                    context_snippet=row["context_snippet"],
                    contradiction_flags=tuple(flags),
                    novelty_score=float(row["novelty_score"] or 1),
                    created_at=row["created_at"],
                ),
            )
        return out

    def upsert_storyline(
        self,
        *,
        storyline_id: str,
        slug: str,
        title: str,
        topic_keys: list[str],
        entity_keys: list[str],
        headline: str,
        summary: str | None,
        source: str | None,
        tone_direction: str | None,
        saturation_score: float,
        cluster_id: int | None = None,
        is_new: bool,
    ) -> StorylineSnapshot:
        now = _utcnow()
        with self._conn() as conn:
            existing = conn.execute(
                "SELECT publish_count, source_diversity_json, first_seen_at FROM editorial_storylines WHERE storyline_id = ?",
                (storyline_id,),
            ).fetchone()
            sources: list[str] = []
            publish_count = 1
            first_seen = now
            if existing:
                publish_count = int(existing["publish_count"]) + 1
                first_seen = existing["first_seen_at"]
                try:
                    sources = json.loads(existing["source_diversity_json"] or "[]")
                except json.JSONDecodeError:
                    sources = []
            if source and source not in sources:
                sources.append(source)

            conn.execute(
                """
                INSERT INTO editorial_storylines (
                    storyline_id, slug, title, topic_keys_json, entity_keys_json,
                    first_seen_at, last_updated_at, publish_count, source_diversity_json,
                    latest_headline, latest_summary, tone_direction, unresolved_json,
                    saturation_score, cluster_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '[]', ?, ?, ?)
                ON CONFLICT(storyline_id) DO UPDATE SET
                    title = excluded.title,
                    topic_keys_json = excluded.topic_keys_json,
                    entity_keys_json = excluded.entity_keys_json,
                    last_updated_at = excluded.last_updated_at,
                    publish_count = excluded.publish_count,
                    source_diversity_json = excluded.source_diversity_json,
                    latest_headline = excluded.latest_headline,
                    latest_summary = excluded.latest_summary,
                    tone_direction = excluded.tone_direction,
                    saturation_score = excluded.saturation_score,
                    cluster_id = COALESCE(excluded.cluster_id, editorial_storylines.cluster_id)
                """,
                (
                    storyline_id,
                    slug,
                    title,
                    json.dumps(topic_keys),
                    json.dumps(entity_keys),
                    first_seen if not is_new else now,
                    now,
                    publish_count,
                    json.dumps(sources),
                    headline[:500],
                    (summary or "")[:2000],
                    tone_direction,
                    saturation_score,
                    cluster_id,
                    first_seen if not is_new else now,
                ),
            )
            conn.commit()
        snap = self.get_storyline(storyline_id)
        assert snap is not None
        return snap

    def record_event(
        self,
        *,
        storyline_id: str,
        pending_news_id: int | None,
        event_type: str,
        follow_up_kind: str,
        headline: str,
        summary: str | None,
        source: str | None,
        tags: list[str],
        context_snippet: str | None,
        contradiction_flags: list[str],
        novelty_score: float,
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO editorial_story_events (
                    storyline_id, pending_news_id, event_type, follow_up_kind,
                    headline, summary, source, tags_json, context_snippet,
                    contradiction_flags_json, novelty_score, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    storyline_id,
                    pending_news_id,
                    event_type,
                    follow_up_kind,
                    headline[:500],
                    (summary or "")[:2000],
                    source,
                    json.dumps(tags),
                    context_snippet,
                    json.dumps(contradiction_flags),
                    novelty_score,
                    _utcnow(),
                ),
            )
            conn.commit()

    def storyline_timeline_payload(self, storyline_id: str) -> dict[str, Any] | None:
        storyline = self.get_storyline(storyline_id)
        if storyline is None:
            return None
        events = self.events_for_storyline(storyline_id, limit=50)
        return {
            "storyline_id": storyline.storyline_id,
            "title": storyline.title,
            "slug": storyline.slug,
            "topic_keys": list(storyline.topic_keys),
            "entities": list(storyline.entity_keys),
            "first_seen_at": storyline.first_seen_at,
            "last_updated_at": storyline.last_updated_at,
            "publish_count": storyline.publish_count,
            "sources": list(storyline.sources),
            "tone_direction": storyline.tone_direction,
            "saturation_score": storyline.saturation_score,
            "latest_headline": storyline.latest_headline,
            "events": [
                {
                    "id": e.id,
                    "pending_news_id": e.pending_news_id,
                    "follow_up_kind": e.follow_up_kind,
                    "headline": e.headline,
                    "source": e.source,
                    "context_snippet": e.context_snippet,
                    "contradiction_flags": list(e.contradiction_flags),
                    "created_at": e.created_at,
                }
                for e in events
            ],
        }

    def create_storyline_id_for_content(
        self,
        *,
        headline: str,
        summary: str | None,
        tags: list[str],
    ) -> tuple[str, str, str, list[str], list[str]]:
        topic_keys = extract_topic_keys(headline, summary or "", tags=tags)
        slug = primary_storyline_slug(topic_keys)
        sid = storyline_id_from_slug(slug)
        entities = extract_entity_keys(headline, summary)
        title = headline.strip()[:120] or slug.replace("-", " ").title()
        return sid, slug, title, topic_keys, entities
