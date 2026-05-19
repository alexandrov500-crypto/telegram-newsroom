from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from bot.processing.languages import normalize_language_code

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class NewsLocalization:
    id: int
    pending_news_id: int
    language: str
    translated_title: str
    translated_summary: str | None
    localized_headline: str | None
    localized_hook: str | None
    created_at: str


class LocalizationRepository:
    """Per-language story variants for pending news and clusters."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def upsert_localization(
        self,
        *,
        pending_news_id: int,
        language: str,
        translated_title: str,
        translated_summary: str | None,
        localized_headline: str | None,
        localized_hook: str | None,
    ) -> int | None:
        lang = normalize_language_code(language)
        if lang is None:
            return None
        try:
            with self._connect() as conn:
                row = conn.execute(
                    """
                    SELECT id FROM news_localizations
                    WHERE pending_news_id = ? AND language = ?
                    """,
                    (pending_news_id, lang),
                ).fetchone()
                if row is not None:
                    conn.execute(
                        """
                        UPDATE news_localizations
                        SET translated_title = ?, translated_summary = ?,
                            localized_headline = ?, localized_hook = ?
                        WHERE id = ?
                        """,
                        (
                            translated_title,
                            translated_summary,
                            localized_headline,
                            localized_hook,
                            int(row["id"]),
                        ),
                    )
                    conn.commit()
                    return int(row["id"])

                cur = conn.execute(
                    """
                    INSERT INTO news_localizations (
                        pending_news_id, language, translated_title,
                        translated_summary, localized_headline, localized_hook,
                        created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        pending_news_id,
                        lang,
                        translated_title,
                        translated_summary,
                        localized_headline,
                        localized_hook,
                        self._now(),
                    ),
                )
                conn.commit()
                return int(cur.lastrowid)
        except Exception:
            logger.exception(
                "event=localization_failed action=upsert pending_news_id=%d lang=%s",
                pending_news_id,
                language,
            )
            return None

    def get_localization(
        self,
        pending_news_id: int,
        language: str,
    ) -> NewsLocalization | None:
        lang = normalize_language_code(language)
        if lang is None:
            return None
        try:
            with self._connect() as conn:
                row = conn.execute(
                    """
                    SELECT id, pending_news_id, language, translated_title,
                           translated_summary, localized_headline, localized_hook,
                           created_at
                    FROM news_localizations
                    WHERE pending_news_id = ? AND language = ?
                    """,
                    (pending_news_id, lang),
                ).fetchone()
            if row is None:
                return None
            return NewsLocalization(
                id=int(row["id"]),
                pending_news_id=int(row["pending_news_id"]),
                language=str(row["language"]),
                translated_title=str(row["translated_title"]),
                translated_summary=row["translated_summary"],
                localized_headline=row["localized_headline"],
                localized_hook=row["localized_hook"],
                created_at=str(row["created_at"]),
            )
        except Exception:
            logger.exception(
                "event=localization_failed action=get pending_news_id=%d",
                pending_news_id,
            )
            return None

    def list_for_pending(self, pending_news_id: int) -> list[NewsLocalization]:
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT id, pending_news_id, language, translated_title,
                           translated_summary, localized_headline, localized_hook,
                           created_at
                    FROM news_localizations
                    WHERE pending_news_id = ?
                    ORDER BY language ASC
                    """,
                    (pending_news_id,),
                ).fetchall()
            return [
                NewsLocalization(
                    id=int(row["id"]),
                    pending_news_id=int(row["pending_news_id"]),
                    language=str(row["language"]),
                    translated_title=str(row["translated_title"]),
                    translated_summary=row["translated_summary"],
                    localized_headline=row["localized_headline"],
                    localized_hook=row["localized_hook"],
                    created_at=str(row["created_at"]),
                )
                for row in rows
            ]
        except Exception:
            return []

    def list_for_cluster(self, cluster_id: int) -> list[NewsLocalization]:
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT nl.id, nl.pending_news_id, nl.language, nl.translated_title,
                           nl.translated_summary, nl.localized_headline, nl.localized_hook,
                           nl.created_at
                    FROM news_localizations nl
                    JOIN pending_news p ON p.id = nl.pending_news_id
                    WHERE p.cluster_id = ?
                    ORDER BY nl.language ASC, nl.id DESC
                    """,
                    (cluster_id,),
                ).fetchall()
            return [
                NewsLocalization(
                    id=int(row["id"]),
                    pending_news_id=int(row["pending_news_id"]),
                    language=str(row["language"]),
                    translated_title=str(row["translated_title"]),
                    translated_summary=row["translated_summary"],
                    localized_headline=row["localized_headline"],
                    localized_hook=row["localized_hook"],
                    created_at=str(row["created_at"]),
                )
                for row in rows
            ]
        except Exception:
            return []
