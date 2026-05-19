from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from bot.processing.semantic import (
    best_cluster_match,
    build_fingerprint,
    tokens_to_storage,
)

logger = logging.getLogger(__name__)


class ClusterAttachOutcome(str, Enum):
    NEW_CLUSTER = "new_cluster"
    MATCHED = "matched"
    DUPLICATE_LINK = "duplicate_link"
    ERROR_FALLBACK = "error_fallback"


@dataclass(frozen=True)
class ClusterAttachResult:
    outcome: ClusterAttachOutcome
    cluster_id: int | None = None
    similarity: float | None = None
    should_enqueue: bool = False


@dataclass(frozen=True)
class PendingClusterView:
    sources: tuple[str, ...]
    variant_count: int


class ClusterRepository:
    """SQLite story clusters for semantic deduplication."""

    def __init__(self, db_path: Path, *, similarity_threshold: float = 0.72) -> None:
        self._db_path = db_path
        self._threshold = similarity_threshold

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        return conn

    def link_exists(self, link: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM story_cluster_items WHERE link = ? LIMIT 1",
                (link,),
            ).fetchone()
        return row is not None

    def find_matching_cluster_id(self, title: str) -> int | None:
        """Preview semantic match without persisting a variant."""
        try:
            fingerprint, _ = build_fingerprint(title)
            with self._connect() as conn:
                candidates = self._load_cluster_candidates(conn)
            threshold = self._threshold
            try:
                from bot.editorial.flow_health.adaptive import effective_cluster_threshold

                threshold = effective_cluster_threshold()
            except Exception:
                pass
            match = best_cluster_match(
                fingerprint,
                candidates,
                threshold=threshold,
            )
            return int(match[0]) if match is not None else None
        except Exception:
            logger.exception("event=find_matching_cluster_failed title=%r", title[:80])
            return None

    def _load_cluster_candidates(self, conn: sqlite3.Connection) -> list[tuple[int, str]]:
        rows = conn.execute(
            """
            SELECT id, embedding_hash
            FROM story_clusters
            ORDER BY id DESC
            LIMIT 500
            """
        ).fetchall()
        return [(int(row["id"]), str(row["embedding_hash"])) for row in rows]

    def _create_cluster(
        self,
        conn: sqlite3.Connection,
        *,
        title: str,
        summary: str | None,
        fingerprint_storage: str,
        embedding_hash: str,
    ) -> int:
        created_at = datetime.now(timezone.utc).isoformat()
        cur = conn.execute(
            """
            INSERT INTO story_clusters (
                canonical_title, canonical_summary, embedding_hash, created_at
            ) VALUES (?, ?, ?, ?)
            """,
            (title, summary, fingerprint_storage, created_at),
        )
        cluster_id = int(cur.lastrowid)
        logger.info(
            "event=semantic_cluster_created cluster_id=%d embedding_hash=%r title=%r",
            cluster_id,
            embedding_hash,
            title[:80],
        )
        return cluster_id

    def _add_cluster_item(
        self,
        conn: sqlite3.Connection,
        *,
        cluster_id: int,
        source: str | None,
        title: str,
        link: str,
    ) -> None:
        created_at = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """
            INSERT INTO story_cluster_items (cluster_id, source, title, link, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (cluster_id, source, title, link, created_at),
        )

    def attach_story_variant(
        self,
        *,
        title: str,
        summary: str | None,
        link: str,
        source: str | None,
    ) -> ClusterAttachResult:
        """
        Match or create a cluster for a story variant.

        Fail-open: on unexpected errors, creates a new cluster and signals enqueue.
        """
        try:
            fingerprint, embedding_hash = build_fingerprint(title)
            fingerprint_storage = tokens_to_storage(fingerprint)

            with self._connect() as conn:
                if conn.execute(
                    "SELECT 1 FROM story_cluster_items WHERE link = ? LIMIT 1",
                    (link,),
                ).fetchone():
                    return ClusterAttachResult(
                        outcome=ClusterAttachOutcome.DUPLICATE_LINK,
                        cluster_id=None,
                    )

                threshold = self._threshold
                try:
                    from bot.editorial.flow_health.adaptive import effective_cluster_threshold

                    threshold = effective_cluster_threshold()
                except Exception:
                    pass
                candidates = self._load_cluster_candidates(conn)
                match = best_cluster_match(
                    fingerprint,
                    candidates,
                    threshold=threshold,
                )

                if match is not None:
                    cluster_id, score = match
                    logger.info(
                        "event=semantic_cluster_matched cluster_id=%d "
                        "event=semantic_similarity_score score=%.4f link=%r",
                        cluster_id,
                        score,
                        link,
                    )
                    self._add_cluster_item(
                        conn,
                        cluster_id=cluster_id,
                        source=source,
                        title=title,
                        link=link,
                    )
                    conn.commit()
                    should_enqueue = False
                    try:
                        from bot.editorial.flow_health.floor import should_force_cluster_enqueue

                        if should_force_cluster_enqueue(headline=title):
                            should_enqueue = True
                    except Exception:
                        pass
                    return ClusterAttachResult(
                        outcome=ClusterAttachOutcome.MATCHED,
                        cluster_id=cluster_id,
                        similarity=score,
                        should_enqueue=should_enqueue,
                    )

                cluster_id = self._create_cluster(
                    conn,
                    title=title,
                    summary=summary,
                    fingerprint_storage=fingerprint_storage,
                    embedding_hash=embedding_hash,
                )
                self._add_cluster_item(
                    conn,
                    cluster_id=cluster_id,
                    source=source,
                    title=title,
                    link=link,
                )
                conn.commit()
                try:
                    from bot.observability.metrics import record_cluster_created

                    record_cluster_created()
                except Exception:
                    pass
                return ClusterAttachResult(
                    outcome=ClusterAttachOutcome.NEW_CLUSTER,
                    cluster_id=cluster_id,
                    should_enqueue=True,
                )
        except Exception:
            logger.exception(
                "event=semantic_fallback_new_cluster link=%r title=%r",
                link,
                title[:80],
            )
            try:
                fingerprint, embedding_hash = build_fingerprint(title)
                with self._connect() as conn:
                    cluster_id = self._create_cluster(
                        conn,
                        title=title,
                        summary=summary,
                        fingerprint_storage=tokens_to_storage(fingerprint),
                        embedding_hash=embedding_hash,
                    )
                    self._add_cluster_item(
                        conn,
                        cluster_id=cluster_id,
                        source=source,
                        title=title,
                        link=link,
                    )
                    conn.commit()
                    return ClusterAttachResult(
                        outcome=ClusterAttachOutcome.ERROR_FALLBACK,
                        cluster_id=cluster_id,
                        should_enqueue=True,
                    )
            except Exception:
                logger.exception(
                    "event=semantic_fallback_new_cluster_failed link=%r",
                    link,
                )
                return ClusterAttachResult(
                    outcome=ClusterAttachOutcome.ERROR_FALLBACK,
                    should_enqueue=True,
                )

    def get_cluster_view(self, cluster_id: int | None) -> PendingClusterView:
        if cluster_id is None:
            return PendingClusterView(sources=(), variant_count=1)
        try:
            with self._connect() as conn:
                count_row = conn.execute(
                    """
                    SELECT COUNT(*) AS cnt
                    FROM story_cluster_items
                    WHERE cluster_id = ?
                    """,
                    (cluster_id,),
                ).fetchone()
                source_rows = conn.execute(
                    """
                    SELECT DISTINCT source
                    FROM story_cluster_items
                    WHERE cluster_id = ? AND source IS NOT NULL AND source != ''
                    ORDER BY source
                    """,
                    (cluster_id,),
                ).fetchall()
            variant_count = int(count_row["cnt"]) if count_row else 1
            sources = tuple(str(row["source"]) for row in source_rows)
            return PendingClusterView(sources=sources, variant_count=max(variant_count, 1))
        except Exception:
            logger.exception(
                "event=cluster_view_failed cluster_id=%s",
                cluster_id,
            )
            return PendingClusterView(sources=(), variant_count=1)
