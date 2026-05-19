from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from bot.editorial.formatting import parse_tags_field
from bot.processing.languages import DEFAULT_SOURCE_LANGUAGE, normalize_language_code
from bot.processing.media import MEDIA_NONE

logger = logging.getLogger(__name__)

STATUS_PENDING = "pending"
STATUS_REJECTED = "rejected"
STATUS_PUBLISHED = "published"

_PENDING_SELECT = """
    id, title, summary, link, tags, source, created_at, status, cluster_id,
    priority_score, priority_reason, source_count,
    media_type, media_url, thumbnail_url, media_width, media_height,
    optimized_headline, hook_line, caption_style,
    source_language, target_language, translated_title, translated_summary,
    localized_headline, localized_hook
"""


@dataclass(frozen=True)
class PendingNewsItem:
    id: int
    title: str
    summary: str | None
    link: str
    tags: list[str]
    source: str | None
    created_at: str
    status: str
    cluster_id: int | None = None
    variant_count: int = 1
    sources: tuple[str, ...] = ()
    priority_score: float = 0.5
    priority_reason: str | None = None
    source_count: int = 1
    media_type: str = MEDIA_NONE
    media_url: str | None = None
    thumbnail_url: str | None = None
    media_width: int | None = None
    media_height: int | None = None
    optimized_headline: str | None = None
    hook_line: str | None = None
    caption_style: str = "optimized"
    source_language: str = DEFAULT_SOURCE_LANGUAGE
    target_language: str | None = None
    translated_title: str | None = None
    translated_summary: str | None = None
    localized_headline: str | None = None
    localized_hook: str | None = None


def _optional_int(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


class EditorialRepository:
    """SQLite-backed editorial moderation queue."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _row_to_item(row: sqlite3.Row) -> PendingNewsItem:
        cluster_id = row["cluster_id"]
        raw_score = row["priority_score"]
        return PendingNewsItem(
            id=int(row["id"]),
            title=str(row["title"]),
            summary=row["summary"],
            link=str(row["link"]),
            tags=parse_tags_field(row["tags"]),
            source=row["source"],
            created_at=str(row["created_at"]),
            status=str(row["status"]),
            cluster_id=int(cluster_id) if cluster_id is not None else None,
            priority_score=float(raw_score) if raw_score is not None else 0.5,
            priority_reason=row["priority_reason"],
            source_count=int(row["source_count"] or 1),
            media_type=str(row["media_type"] or MEDIA_NONE),
            media_url=row["media_url"],
            thumbnail_url=row["thumbnail_url"],
            media_width=_optional_int(row["media_width"]),
            media_height=_optional_int(row["media_height"]),
            optimized_headline=row["optimized_headline"],
            hook_line=row["hook_line"],
            caption_style=str(row["caption_style"] or "optimized"),
            source_language=str(row["source_language"] or DEFAULT_SOURCE_LANGUAGE),
            target_language=row["target_language"],
            translated_title=row["translated_title"],
            translated_summary=row["translated_summary"],
            localized_headline=row["localized_headline"],
            localized_hook=row["localized_hook"],
        )

    def enqueue_news(
        self,
        *,
        title: str,
        summary: str | None,
        link: str,
        tags: list[str] | None = None,
        source: str | None = None,
        cluster_id: int | None = None,
        priority_score: float = 0.5,
        priority_reason: str | None = None,
        source_count: int = 1,
        media_type: str = MEDIA_NONE,
        media_url: str | None = None,
        thumbnail_url: str | None = None,
        media_width: int | None = None,
        media_height: int | None = None,
        optimized_headline: str | None = None,
        hook_line: str | None = None,
        caption_style: str = "optimized",
        source_language: str = DEFAULT_SOURCE_LANGUAGE,
        target_language: str | None = None,
        translated_title: str | None = None,
        translated_summary: str | None = None,
        localized_headline: str | None = None,
        localized_hook: str | None = None,
    ) -> int | None:
        """Insert a pending item. Returns new id, or None if link already exists."""
        created_at = datetime.now(timezone.utc).isoformat()
        tags_json = json.dumps(tags or [])
        try:
            with self._connect() as conn:
                cur = conn.execute(
                    f"""
                    INSERT INTO pending_news (
                        title, summary, link, tags, source, created_at, status,
                        cluster_id, priority_score, priority_reason, source_count,
                        media_type, media_url, thumbnail_url, media_width, media_height,
                        optimized_headline, hook_line, caption_style,
                        source_language, target_language, translated_title,
                        translated_summary, localized_headline, localized_hook
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        title,
                        summary,
                        link,
                        tags_json,
                        source,
                        created_at,
                        STATUS_PENDING,
                        cluster_id,
                        priority_score,
                        priority_reason,
                        source_count,
                        media_type,
                        media_url,
                        thumbnail_url,
                        media_width,
                        media_height,
                        optimized_headline,
                        hook_line,
                        caption_style,
                        normalize_language_code(source_language)
                        or DEFAULT_SOURCE_LANGUAGE,
                        target_language,
                        translated_title,
                        translated_summary,
                        localized_headline,
                        localized_hook,
                    ),
                )
                conn.commit()
                return int(cur.lastrowid)
        except sqlite3.IntegrityError:
            logger.info(
                "event=editorial_duplicate_skipped link=%r reason=unique_constraint",
                link,
            )
            return None

    def update_priority(
        self,
        news_id: int,
        *,
        priority_score: float,
        priority_reason: str | None,
        source_count: int,
    ) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                """
                UPDATE pending_news
                SET priority_score = ?, priority_reason = ?, source_count = ?
                WHERE id = ? AND status = ?
                """,
                (priority_score, priority_reason, source_count, news_id, STATUS_PENDING),
            )
            conn.commit()
            return cur.rowcount > 0

    def get_pending_by_cluster_id(self, cluster_id: int) -> PendingNewsItem | None:
        with self._connect() as conn:
            row = conn.execute(
                f"""
                SELECT {_PENDING_SELECT}
                FROM pending_news
                WHERE cluster_id = ? AND status = ?
                ORDER BY id ASC
                LIMIT 1
                """,
                (cluster_id, STATUS_PENDING),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_item(row)

    def link_exists(self, link: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM pending_news WHERE link = ? LIMIT 1",
                (link,),
            ).fetchone()
        return row is not None

    def get_pending_news(
        self,
        *,
        limit: int = 10,
        cluster_views: dict[int, tuple[tuple[str, ...], int]] | None = None,
    ) -> list[PendingNewsItem]:
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT {_PENDING_SELECT}
                FROM pending_news
                WHERE status = ?
                ORDER BY priority_score DESC, created_at DESC
                LIMIT ?
                """,
                (STATUS_PENDING, limit),
            ).fetchall()
        items: list[PendingNewsItem] = []
        for row in rows:
            item = self._row_to_item(row)
            cluster_id = item.cluster_id
            if cluster_id is not None and cluster_views and cluster_id in cluster_views:
                sources, variant_count = cluster_views[cluster_id]
                item = PendingNewsItem(
                    id=item.id,
                    title=item.title,
                    summary=item.summary,
                    link=item.link,
                    tags=item.tags,
                    source=item.source,
                    created_at=item.created_at,
                    status=item.status,
                    cluster_id=cluster_id,
                    variant_count=variant_count,
                    sources=sources,
                    priority_score=item.priority_score,
                    priority_reason=item.priority_reason,
                    source_count=max(item.source_count, len(sources)),
                    media_type=item.media_type,
                    media_url=item.media_url,
                    thumbnail_url=item.thumbnail_url,
                    media_width=item.media_width,
                    media_height=item.media_height,
                    optimized_headline=item.optimized_headline,
                    hook_line=item.hook_line,
                    caption_style=item.caption_style,
                    source_language=item.source_language,
                    target_language=item.target_language,
                    translated_title=item.translated_title,
                    translated_summary=item.translated_summary,
                    localized_headline=item.localized_headline,
                    localized_hook=item.localized_hook,
                )
            items.append(item)
        return items

    def update_language_fields(
        self,
        news_id: int,
        *,
        source_language: str | None = None,
        target_language: str | None = None,
        translated_title: str | None = None,
        translated_summary: str | None = None,
        localized_headline: str | None = None,
        localized_hook: str | None = None,
    ) -> bool:
        fields: list[str] = []
        values: list[object] = []
        if source_language is not None:
            fields.append("source_language = ?")
            values.append(
                normalize_language_code(source_language) or DEFAULT_SOURCE_LANGUAGE
            )
        if target_language is not None:
            fields.append("target_language = ?")
            values.append(normalize_language_code(target_language))
        if translated_title is not None:
            fields.append("translated_title = ?")
            values.append(translated_title)
        if translated_summary is not None:
            fields.append("translated_summary = ?")
            values.append(translated_summary)
        if localized_headline is not None:
            fields.append("localized_headline = ?")
            values.append(localized_headline)
        if localized_hook is not None:
            fields.append("localized_hook = ?")
            values.append(localized_hook)
        if not fields:
            return False
        values.append(news_id)
        with self._connect() as conn:
            cur = conn.execute(
                f"UPDATE pending_news SET {', '.join(fields)} WHERE id = ?",
                values,
            )
            conn.commit()
            return cur.rowcount > 0

    def update_headlines(
        self,
        news_id: int,
        *,
        optimized_headline: str | None,
        hook_line: str | None,
        caption_style: str | None = None,
    ) -> bool:
        with self._connect() as conn:
            if caption_style is not None:
                cur = conn.execute(
                    """
                    UPDATE pending_news
                    SET optimized_headline = ?, hook_line = ?, caption_style = ?
                    WHERE id = ?
                    """,
                    (optimized_headline, hook_line, caption_style, news_id),
                )
            else:
                cur = conn.execute(
                    """
                    UPDATE pending_news
                    SET optimized_headline = ?, hook_line = ?
                    WHERE id = ?
                    """,
                    (optimized_headline, hook_line, news_id),
                )
            conn.commit()
            return cur.rowcount > 0

    def get_by_id(self, news_id: int) -> PendingNewsItem | None:
        with self._connect() as conn:
            row = conn.execute(
                f"""
                SELECT {_PENDING_SELECT}
                FROM pending_news
                WHERE id = ?
                """,
                (news_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_item(row)

    def approve_news(self, news_id: int) -> PendingNewsItem | None:
        """Return the item if it is still pending (ready for approval flow)."""
        item = self.get_by_id(news_id)
        if item is None or item.status != STATUS_PENDING:
            return None
        return item

    def reject_news(self, news_id: int) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                """
                UPDATE pending_news
                SET status = ?
                WHERE id = ? AND status = ?
                """,
                (STATUS_REJECTED, news_id, STATUS_PENDING),
            )
            conn.commit()
            return cur.rowcount > 0

    def mark_published(self, news_id: int) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                """
                UPDATE pending_news
                SET status = ?
                WHERE id = ? AND status = ?
                """,
                (STATUS_PUBLISHED, news_id, STATUS_PENDING),
            )
            conn.commit()
            return cur.rowcount > 0
