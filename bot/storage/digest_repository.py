from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from bot.editorial.formatting import parse_tags_field
from bot.processing.media import MEDIA_NONE
from bot.storage.editorial_repository import STATUS_PUBLISHED

_PENDING_SELECT = """
    id, title, summary, link, tags, source, created_at, status, cluster_id,
    priority_score, priority_reason, source_count,
    media_type, media_url, thumbnail_url, media_width, media_height
"""

logger = logging.getLogger(__name__)

DIGEST_MORNING = "morning"
DIGEST_HOURLY = "hourly"


def _optional_int(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class DigestCandidate:
    id: int
    title: str
    summary: str | None
    link: str
    tags: list[str]
    cluster_id: int | None
    priority_score: float
    created_at: str
    media_type: str = MEDIA_NONE
    media_url: str | None = None
    thumbnail_url: str | None = None
    media_width: int | None = None
    media_height: int | None = None


@dataclass(frozen=True)
class DigestRecord:
    id: int
    digest_type: str
    title: str
    content: str
    created_at: str
    published_at: str | None
    item_count: int


class DigestRepository:
    """SQLite persistence for digests."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _row_to_candidate(row: sqlite3.Row) -> DigestCandidate:
        cluster_id = row["cluster_id"]
        raw_score = row["priority_score"]
        return DigestCandidate(
            id=int(row["id"]),
            title=str(row["title"]),
            summary=row["summary"],
            link=str(row["link"]),
            tags=parse_tags_field(row["tags"]),
            cluster_id=int(cluster_id) if cluster_id is not None else None,
            priority_score=float(raw_score) if raw_score is not None else 0.5,
            created_at=str(row["created_at"]),
            media_type=str(row["media_type"] or MEDIA_NONE),
            media_url=row["media_url"],
            thumbnail_url=row["thumbnail_url"],
            media_width=_optional_int(row["media_width"]),
            media_height=_optional_int(row["media_height"]),
        )

    def get_undigested_published(
        self,
        *,
        limit: int = 50,
        since_iso: str | None = None,
        digest_type: str | None = None,
        language: str = "en",
    ) -> list[DigestCandidate]:
        query = f"""
            SELECT {_PENDING_SELECT}
            FROM pending_news p
            WHERE p.status = ?
              AND p.id NOT IN (
                SELECT di.pending_news_id
                FROM digest_items di
                JOIN digests d ON d.id = di.digest_id
                WHERE COALESCE(d.language, 'en') = ?
                  AND (? IS NULL OR d.digest_type = ?)
              )
        """
        params: list[object] = [STATUS_PUBLISHED, language, digest_type, digest_type]
        if since_iso:
            query += " AND p.created_at >= ?"
            params.append(since_iso)
        query += " ORDER BY p.priority_score DESC, p.created_at DESC LIMIT ?"
        params.append(limit)

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_to_candidate(row) for row in rows]

    def create_digest(
        self,
        *,
        digest_type: str,
        title: str,
        content: str,
        item_count: int,
        language: str = "en",
    ) -> int:
        created_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO digests (
                    digest_type, title, content, created_at, published_at,
                    item_count, language
                ) VALUES (?, ?, ?, ?, NULL, ?, ?)
                """,
                (digest_type, title, content, created_at, item_count, language),
            )
            conn.commit()
            return int(cur.lastrowid)

    def add_digest_items(self, digest_id: int, pending_news_ids: list[int]) -> None:
        if not pending_news_ids:
            return
        created_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO digest_items (digest_id, pending_news_id)
                VALUES (?, ?)
                """,
                [(digest_id, news_id) for news_id in pending_news_ids],
            )
            conn.commit()

    def mark_digest_published(self, digest_id: int) -> None:
        published_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                "UPDATE digests SET published_at = ? WHERE id = ?",
                (published_at, digest_id),
            )
            conn.commit()
