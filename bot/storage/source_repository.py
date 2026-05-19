from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from bot.processing.source_reliability import (
    DEFAULT_TRUST,
    SOURCE_TYPE_UNKNOWN,
    approval_ratio,
    clamp_trust,
    detect_source_type,
    initial_trust_score,
    normalize_source_name,
)

logger = logging.getLogger(__name__)

EVENT_REGISTERED = "registered"
EVENT_APPROVED = "approved"
EVENT_REJECTED = "rejected"

APPROVE_DELTA = 0.03
REJECT_DELTA = -0.04


@dataclass(frozen=True)
class SourceProfile:
    source_name: str
    source_type: str
    trust_score: float
    article_count: int
    accepted_count: int
    rejected_count: int
    approval_ratio: float


class SourceRepository:
    """SQLite-backed source reputation store."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _row_to_profile(row: sqlite3.Row) -> SourceProfile:
        accepted = int(row["accepted_count"] or 0)
        rejected = int(row["rejected_count"] or 0)
        return SourceProfile(
            source_name=str(row["source_name"]),
            source_type=str(row["source_type"]),
            trust_score=float(row["trust_score"]),
            article_count=int(row["article_count"] or 0),
            accepted_count=accepted,
            rejected_count=rejected,
            approval_ratio=approval_ratio(
                accepted_count=accepted,
                rejected_count=rejected,
            ),
        )

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _log_event(
        self,
        conn: sqlite3.Connection,
        *,
        source_name: str,
        event_type: str,
        score_delta: float | None,
    ) -> None:
        conn.execute(
            """
            INSERT INTO source_events (source_name, event_type, score_delta, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (source_name, event_type, score_delta, self._now()),
        )

    def _apply_trust_delta(
        self,
        conn: sqlite3.Connection,
        *,
        source_name: str,
        delta: float,
        event_type: str,
    ) -> float:
        row = conn.execute(
            "SELECT trust_score FROM sources WHERE source_name = ?",
            (source_name,),
        ).fetchone()
        if row is None:
            return DEFAULT_TRUST

        old_trust = float(row["trust_score"])
        new_trust = clamp_trust(old_trust + delta)
        conn.execute(
            """
            UPDATE sources
            SET trust_score = ?, updated_at = ?
            WHERE source_name = ?
            """,
            (new_trust, self._now(), source_name),
        )
        self._log_event(
            conn,
            source_name=source_name,
            event_type=event_type,
            score_delta=delta,
        )
        logger.info(
            "event=source_trust_updated source=%r old=%.3f new=%.3f delta=%.3f event=%s",
            source_name,
            old_trust,
            new_trust,
            delta,
            event_type,
        )
        if new_trust >= 0.8 and old_trust < 0.8:
            logger.info("event=source_high_trust_detected source=%r score=%.3f", source_name, new_trust)
        if new_trust <= 0.25 and old_trust > 0.25:
            logger.info("event=source_low_trust_detected source=%r score=%.3f", source_name, new_trust)
        return new_trust

    def get_profile(self, raw_source: str | None) -> SourceProfile:
        """Read source reputation without incrementing article_count."""
        try:
            source_name = normalize_source_name(raw_source)
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT * FROM sources WHERE source_name = ?",
                    (source_name,),
                ).fetchone()
            if row is None:
                source_type = detect_source_type(source_name)
                trust = initial_trust_score(source_name, source_type)
                return SourceProfile(
                    source_name=source_name,
                    source_type=source_type,
                    trust_score=trust,
                    article_count=0,
                    accepted_count=0,
                    rejected_count=0,
                    approval_ratio=0.5,
                )
            return self._row_to_profile(row)
        except Exception:
            logger.exception("event=source_profile_failed raw_source=%r", raw_source)
            return SourceProfile(
                source_name=normalize_source_name(raw_source),
                source_type=SOURCE_TYPE_UNKNOWN,
                trust_score=DEFAULT_TRUST,
                article_count=0,
                accepted_count=0,
                rejected_count=0,
                approval_ratio=0.5,
            )

    def touch_source(self, raw_source: str | None) -> SourceProfile:
        """
        Register or update a source on ingest. Never raises.
        """
        try:
            source_name = normalize_source_name(raw_source)
            source_type = detect_source_type(source_name)
            now = self._now()

            with self._connect() as conn:
                row = conn.execute(
                    "SELECT * FROM sources WHERE source_name = ?",
                    (source_name,),
                ).fetchone()

                if row is None:
                    trust = initial_trust_score(source_name, source_type)
                    conn.execute(
                        """
                        INSERT INTO sources (
                            source_name, source_type, trust_score,
                            article_count, accepted_count, rejected_count,
                            created_at, updated_at
                        ) VALUES (?, ?, ?, 1, 0, 0, ?, ?)
                        """,
                        (source_name, source_type, trust, now, now),
                    )
                    self._log_event(
                        conn,
                        source_name=source_name,
                        event_type=EVENT_REGISTERED,
                        score_delta=trust,
                    )
                    conn.commit()
                    logger.info(
                        "event=source_registered source=%r type=%s trust=%.3f",
                        source_name,
                        source_type,
                        trust,
                    )
                    return SourceProfile(
                        source_name=source_name,
                        source_type=source_type,
                        trust_score=trust,
                        article_count=1,
                        accepted_count=0,
                        rejected_count=0,
                        approval_ratio=0.5,
                    )

                conn.execute(
                    """
                    UPDATE sources
                    SET article_count = article_count + 1, updated_at = ?
                    WHERE source_name = ?
                    """,
                    (now, source_name),
                )
                conn.commit()
                updated = conn.execute(
                    "SELECT * FROM sources WHERE source_name = ?",
                    (source_name,),
                ).fetchone()
                assert updated is not None
                return self._row_to_profile(updated)
        except Exception:
            logger.exception(
                "event=source_touch_failed raw_source=%r",
                raw_source,
            )
            return SourceProfile(
                source_name=normalize_source_name(raw_source),
                source_type=SOURCE_TYPE_UNKNOWN,
                trust_score=0.5,
                article_count=0,
                accepted_count=0,
                rejected_count=0,
                approval_ratio=0.5,
            )

    def _ensure_source(self, conn: sqlite3.Connection, source_name: str) -> None:
        row = conn.execute(
            "SELECT 1 FROM sources WHERE source_name = ?",
            (source_name,),
        ).fetchone()
        if row is not None:
            return
        source_type = detect_source_type(source_name)
        trust = initial_trust_score(source_name, source_type)
        now = self._now()
        conn.execute(
            """
            INSERT INTO sources (
                source_name, source_type, trust_score,
                article_count, accepted_count, rejected_count,
                created_at, updated_at
            ) VALUES (?, ?, ?, 0, 0, 0, ?, ?)
            """,
            (source_name, source_type, trust, now, now),
        )
        self._log_event(
            conn,
            source_name=source_name,
            event_type=EVENT_REGISTERED,
            score_delta=trust,
        )
        logger.info(
            "event=source_registered source=%r type=%s trust=%.3f",
            source_name,
            source_type,
            trust,
        )

    def record_approval(self, raw_source: str | None) -> None:
        try:
            source_name = normalize_source_name(raw_source)
            with self._connect() as conn:
                self._ensure_source(conn, source_name)
                conn.execute(
                    """
                    UPDATE sources
                    SET accepted_count = accepted_count + 1, updated_at = ?
                    WHERE source_name = ?
                    """,
                    (self._now(), source_name),
                )
                self._apply_trust_delta(
                    conn,
                    source_name=source_name,
                    delta=APPROVE_DELTA,
                    event_type=EVENT_APPROVED,
                )
                conn.commit()
        except Exception:
            logger.exception("event=source_approval_failed source=%r", raw_source)

    def record_rejection(self, raw_source: str | None) -> None:
        try:
            source_name = normalize_source_name(raw_source)
            with self._connect() as conn:
                self._ensure_source(conn, source_name)
                conn.execute(
                    """
                    UPDATE sources
                    SET rejected_count = rejected_count + 1, updated_at = ?
                    WHERE source_name = ?
                    """,
                    (self._now(), source_name),
                )
                self._apply_trust_delta(
                    conn,
                    source_name=source_name,
                    delta=REJECT_DELTA,
                    event_type=EVENT_REJECTED,
                )
                conn.commit()
        except Exception:
            logger.exception("event=source_rejection_failed source=%r", raw_source)

    def get_source(self, name_query: str) -> SourceProfile | None:
        try:
            key = normalize_source_name(name_query)
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT * FROM sources WHERE source_name = ?",
                    (key,),
                ).fetchone()
                if row is not None:
                    return self._row_to_profile(row)
                row = conn.execute(
                    """
                    SELECT * FROM sources
                    WHERE source_name LIKE ?
                    ORDER BY trust_score DESC
                    LIMIT 1
                    """,
                    (f"%{key}%",),
                ).fetchone()
            if row is None:
                return None
            return self._row_to_profile(row)
        except Exception:
            logger.exception("event=source_lookup_failed query=%r", name_query)
            return None

    def top_sources(self, *, limit: int = 10) -> list[SourceProfile]:
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT * FROM sources
                    ORDER BY trust_score DESC, article_count DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
            return [self._row_to_profile(row) for row in rows]
        except Exception:
            logger.exception("event=source_top_failed")
            return []

    def low_trust_sources(self, *, limit: int = 10, threshold: float = 0.35) -> list[SourceProfile]:
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT * FROM sources
                    WHERE trust_score <= ?
                    ORDER BY trust_score ASC, article_count DESC
                    LIMIT ?
                    """,
                    (threshold, limit),
                ).fetchall()
            return [self._row_to_profile(row) for row in rows]
        except Exception:
            logger.exception("event=source_low_trust_failed")
            return []
