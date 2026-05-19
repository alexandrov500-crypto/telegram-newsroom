from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from bot.processing.adaptive import (
    SIGNAL_ENTITY,
    SIGNAL_HEADLINE,
    SIGNAL_HOOK,
    SIGNAL_TOPIC,
    headline_pattern_key,
    hook_signal_key,
    language_signal_key,
)
from bot.processing.languages import LANG_EN, normalize_language_code
from bot.processing.engagement import calculate_engagement_score

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PublishedPost:
    id: int
    telegram_message_id: int | None
    cluster_id: int | None
    pending_news_id: int | None
    published_at: str
    headline: str | None
    hook_line: str | None
    entities_json: str | None
    topics_json: str | None
    priority_score: float
    source_trust: float
    latest_engagement: float = 0.0
    latest_views: int = 0


@dataclass(frozen=True)
class PostPerformance:
    published_post_id: int
    headline: str | None
    hook_line: str | None
    engagement_score: float
    views: int
    forwards: int
    reactions: int
    published_at: str


@dataclass(frozen=True)
class SignalStat:
    signal_type: str
    signal_key: str
    sample_count: int
    avg_engagement: float


class AnalyticsRepository:
    """Published post tracking, analytics snapshots, and adaptive signals."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def record_published_post(
        self,
        *,
        telegram_message_id: int | None,
        pending_news_id: int | None,
        cluster_id: int | None,
        headline: str | None,
        hook_line: str | None,
        entities: list[str] | None = None,
        topics: list[str] | None = None,
        priority_score: float = 0.5,
        source_trust: float = 0.5,
        language: str = LANG_EN,
    ) -> int | None:
        lang = normalize_language_code(language) or LANG_EN
        try:
            with self._connect() as conn:
                cur = conn.execute(
                    """
                    INSERT INTO published_posts (
                        telegram_message_id, cluster_id, pending_news_id,
                        published_at, headline, hook_line, entities_json,
                        topics_json, priority_score, source_trust, language
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        telegram_message_id,
                        cluster_id,
                        pending_news_id,
                        self._now(),
                        headline,
                        hook_line,
                        json.dumps(entities or []),
                        json.dumps(topics or []),
                        priority_score,
                        source_trust,
                        lang,
                    ),
                )
                conn.commit()
                post_id = int(cur.lastrowid)
            logger.info(
                "event=analytics_collected action=record_post id=%d message_id=%s",
                post_id,
                telegram_message_id,
            )
            return post_id
        except Exception:
            logger.exception("event=analytics_collected action=record_post_failed")
            return None

    def list_posts_for_collection(
        self,
        *,
        limit: int = 40,
        max_age_hours: int = 168,
    ) -> list[PublishedPost]:
        since = (datetime.now(timezone.utc) - timedelta(hours=max_age_hours)).isoformat()
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT
                        p.id, p.telegram_message_id, p.cluster_id, p.pending_news_id,
                        p.published_at, p.headline, p.hook_line, p.entities_json,
                        p.topics_json, p.priority_score, p.source_trust,
                        COALESCE(a.engagement_score, 0) AS latest_engagement,
                        COALESCE(a.views, 0) AS latest_views
                    FROM published_posts p
                    LEFT JOIN post_analytics a ON a.id = (
                        SELECT id FROM post_analytics
                        WHERE published_post_id = p.id
                        ORDER BY collected_at DESC
                        LIMIT 1
                    )
                    WHERE p.telegram_message_id IS NOT NULL
                      AND p.published_at >= ?
                    ORDER BY p.published_at DESC
                    LIMIT ?
                    """,
                    (since, limit),
                ).fetchall()
            return [self._row_to_post(row) for row in rows]
        except Exception:
            logger.exception("event=analytics_collected action=list_failed")
            return []

    @staticmethod
    def _row_to_post(row: sqlite3.Row) -> PublishedPost:
        return PublishedPost(
            id=int(row["id"]),
            telegram_message_id=row["telegram_message_id"],
            cluster_id=row["cluster_id"],
            pending_news_id=row["pending_news_id"],
            published_at=str(row["published_at"]),
            headline=row["headline"],
            hook_line=row["hook_line"],
            entities_json=row["entities_json"],
            topics_json=row["topics_json"],
            priority_score=float(row["priority_score"] or 0.5),
            source_trust=float(row["source_trust"] or 0.5),
            latest_engagement=float(row["latest_engagement"] or 0),
            latest_views=int(row["latest_views"] or 0),
        )

    def record_analytics_snapshot(
        self,
        published_post_id: int,
        *,
        views: int,
        forwards: int,
        reactions: int,
        source_trust: float,
        topic_virality: float,
    ) -> float | None:
        try:
            score = calculate_engagement_score(
                views=views,
                forwards=forwards,
                reactions=reactions,
                source_trust=source_trust,
                topic_virality=topic_virality,
            )
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO post_analytics (
                        published_post_id, views, forwards, reactions,
                        engagement_score, collected_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        published_post_id,
                        views,
                        forwards,
                        reactions,
                        score,
                        self._now(),
                    ),
                )
                conn.commit()
            logger.info(
                "event=engagement_score_updated post_id=%d score=%.3f views=%d",
                published_post_id,
                score,
                views,
            )
            return score
        except Exception:
            logger.exception(
                "event=analytics_collected action=snapshot_failed post_id=%d",
                published_post_id,
            )
            return None

    def _update_signal(self, signal_type: str, signal_key: str, engagement: float) -> None:
        if not signal_key:
            return
        now = self._now()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT sample_count, avg_engagement
                FROM adaptive_signals
                WHERE signal_type = ? AND signal_key = ?
                """,
                (signal_type, signal_key),
            ).fetchone()
            if row is None:
                conn.execute(
                    """
                    INSERT INTO adaptive_signals (
                        signal_type, signal_key, sample_count, avg_engagement, updated_at
                    ) VALUES (?, ?, 1, ?, ?)
                    """,
                    (signal_type, signal_key, engagement, now),
                )
            else:
                count = int(row["sample_count"] or 0) + 1
                prev = float(row["avg_engagement"] or 0.5)
                avg = ((prev * (count - 1)) + engagement) / count
                conn.execute(
                    """
                    UPDATE adaptive_signals
                    SET sample_count = ?, avg_engagement = ?, updated_at = ?
                    WHERE signal_type = ? AND signal_key = ?
                    """,
                    (count, avg, now, signal_type, signal_key),
                )
            conn.commit()

    def learn_from_post(
        self,
        post: PublishedPost,
        engagement_score: float,
        *,
        language: str | None = None,
    ) -> None:
        lang = normalize_language_code(language) or LANG_EN
        try:
            hook_key = hook_signal_key(post.hook_line)
            if hook_key:
                self._update_signal(
                    SIGNAL_HOOK,
                    language_signal_key(hook_key, lang),
                    engagement_score,
                )
            pattern = headline_pattern_key(post.headline)
            self._update_signal(
                SIGNAL_HEADLINE,
                language_signal_key(pattern, lang),
                engagement_score,
            )

            topics = json.loads(post.topics_json or "[]")
            if isinstance(topics, list):
                for topic in topics[:5]:
                    token = str(topic).strip().lower()
                    if token:
                        self._update_signal(
                            SIGNAL_TOPIC,
                            language_signal_key(token, lang),
                            engagement_score,
                        )

            entities = json.loads(post.entities_json or "[]")
            if isinstance(entities, list):
                for entity in entities[:6]:
                    token = str(entity).strip()
                    if token:
                        self._update_signal(
                            SIGNAL_ENTITY,
                            language_signal_key(token.lower(), lang),
                            engagement_score,
                        )
        except Exception:
            logger.exception("event=adaptive_signal_detected action=learn_failed post_id=%d", post.id)

    def topic_virality(
        self,
        topics: list[str],
        *,
        language: str | None = None,
    ) -> float:
        if not topics:
            return 0.5
        lang = normalize_language_code(language) or LANG_EN
        try:
            with self._connect() as conn:
                scores: list[float] = []
                for topic in topics[:5]:
                    key = language_signal_key(str(topic).strip().lower(), lang)
                    row = conn.execute(
                        """
                        SELECT avg_engagement FROM adaptive_signals
                        WHERE signal_type = ? AND signal_key = ?
                        """,
                        (SIGNAL_TOPIC, key),
                    ).fetchone()
                    if row is not None:
                        scores.append(float(row["avg_engagement"] or 0.5))
            if not scores:
                return 0.5
            return sum(scores) / len(scores)
        except Exception:
            return 0.5

    def get_top_signals(
        self,
        signal_type: str,
        *,
        limit: int = 10,
        min_samples: int = 1,
    ) -> list[SignalStat]:
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT signal_type, signal_key, sample_count, avg_engagement
                    FROM adaptive_signals
                    WHERE signal_type = ? AND sample_count >= ?
                    ORDER BY avg_engagement DESC, sample_count DESC
                    LIMIT ?
                    """,
                    (signal_type, min_samples, limit),
                ).fetchall()
            return [
                SignalStat(
                    signal_type=str(row["signal_type"]),
                    signal_key=str(row["signal_key"]),
                    sample_count=int(row["sample_count"] or 0),
                    avg_engagement=float(row["avg_engagement"] or 0),
                )
                for row in rows
            ]
        except Exception:
            logger.exception("event=analytics_collected action=top_signals_failed")
            return []

    def get_top_posts(self, *, limit: int = 10, hours: int = 168) -> list[PostPerformance]:
        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT
                        p.id AS published_post_id,
                        p.headline,
                        p.hook_line,
                        p.published_at,
                        a.engagement_score,
                        a.views,
                        a.forwards,
                        a.reactions
                    FROM published_posts p
                    JOIN post_analytics a ON a.id = (
                        SELECT id FROM post_analytics
                        WHERE published_post_id = p.id
                        ORDER BY collected_at DESC
                        LIMIT 1
                    )
                    WHERE p.published_at >= ?
                    ORDER BY a.engagement_score DESC, a.views DESC
                    LIMIT ?
                    """,
                    (since, limit),
                ).fetchall()
            return [
                PostPerformance(
                    published_post_id=int(row["published_post_id"]),
                    headline=row["headline"],
                    hook_line=row["hook_line"],
                    engagement_score=float(row["engagement_score"] or 0),
                    views=int(row["views"] or 0),
                    forwards=int(row["forwards"] or 0),
                    reactions=int(row["reactions"] or 0),
                    published_at=str(row["published_at"]),
                )
                for row in rows
            ]
        except Exception:
            logger.exception("event=analytics_collected action=top_posts_failed")
            return []

    def get_top_topics(self, *, limit: int = 10) -> list[SignalStat]:
        return self.get_top_signals(SIGNAL_TOPIC, limit=limit)

    def get_best_headline_patterns(self, *, limit: int = 10) -> list[SignalStat]:
        return self.get_top_signals(SIGNAL_HEADLINE, limit=limit, min_samples=1)

    def get_top_entities_by_engagement(self, *, limit: int = 10) -> list[SignalStat]:
        return self.get_top_signals(SIGNAL_ENTITY, limit=limit)

    def get_digest_intelligence(self) -> dict[str, str | None]:
        top_posts = self.get_top_posts(limit=1)
        top_topics = self.get_top_topics(limit=1)
        top_entities = self.get_top_entities_by_engagement(limit=1)
        return {
            "most_engaged_story": top_posts[0].headline if top_posts else None,
            "trending_topic": top_topics[0].signal_key if top_topics else None,
            "top_entity": top_entities[0].signal_key.title() if top_entities else None,
        }

    def analytics_summary(self, *, hours: int = 168) -> dict[str, float | int]:
        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        try:
            with self._connect() as conn:
                row = conn.execute(
                    """
                    SELECT
                        COUNT(DISTINCT p.id) AS post_count,
                        AVG(a.engagement_score) AS avg_engagement,
                        MAX(a.engagement_score) AS max_engagement,
                        SUM(a.views) AS total_views
                    FROM published_posts p
                    LEFT JOIN post_analytics a ON a.published_post_id = p.id
                    WHERE p.published_at >= ?
                    """,
                    (since,),
                ).fetchone()
            if row is None:
                return {"post_count": 0, "avg_engagement": 0.0, "max_engagement": 0.0, "total_views": 0}
            return {
                "post_count": int(row["post_count"] or 0),
                "avg_engagement": float(row["avg_engagement"] or 0),
                "max_engagement": float(row["max_engagement"] or 0),
                "total_views": int(row["total_views"] or 0),
            }
        except Exception:
            logger.exception("event=analytics_collected action=summary_failed")
            return {"post_count": 0, "avg_engagement": 0.0, "max_engagement": 0.0, "total_views": 0}

    def hook_signals_for_generation(self, *, limit: int = 5) -> list[tuple[str, float]]:
        stats = self.get_top_signals(SIGNAL_HOOK, limit=limit, min_samples=2)
        return [(stat.signal_key, stat.avg_engagement) for stat in stats]
