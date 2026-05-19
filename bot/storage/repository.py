from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Protocol

from bot.storage.db import default_db_path, init_database

logger = logging.getLogger(__name__)


class LinkDedup(Protocol):
    def is_seen(self, url: str) -> bool: ...

    def mark_seen(self, url: str) -> None: ...


class SeenLinkRepository:
    """SQLite-backed seen-link store."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        return conn

    def is_seen(self, url: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM seen_links WHERE url = ? LIMIT 1",
                (url,),
            ).fetchone()
        return row is not None

    def mark_seen(self, url: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO seen_links (url) VALUES (?)",
                (url,),
            )
            conn.commit()


class MemoryLinkDedup:
    """In-memory fallback when SQLite is unavailable."""

    def __init__(self) -> None:
        self._seen: set[str] = set()

    def is_seen(self, url: str) -> bool:
        return url in self._seen

    def mark_seen(self, url: str) -> None:
        self._seen.add(url)


class ResilientLinkDedup:
    """SQLite dedup with automatic fallback to in-memory set on errors."""

    def __init__(self, repository: SeenLinkRepository | None) -> None:
        self._repository = repository
        self._fallback = MemoryLinkDedup()

    @property
    def using_database(self) -> bool:
        return self._repository is not None

    def _activate_fallback(self, reason: str) -> None:
        if self._repository is not None:
            logger.warning(
                "event=storage_fallback_in_memory reason=%r",
                reason,
            )
            self._repository = None

    def is_seen(self, url: str) -> bool:
        if self._repository is None:
            return self._fallback.is_seen(url)

        try:
            if self._repository.is_seen(url):
                logger.info("event=dedup_db_hit url=%r", url)
                return True
            logger.debug("event=dedup_db_miss url=%r", url)
            return False
        except sqlite3.Error as exc:
            logger.exception("event=dedup_db_read_failed error=%r", exc)
            self._activate_fallback("is_seen_sqlite_error")
            return self._fallback.is_seen(url)
        except Exception as exc:
            logger.exception("event=dedup_db_read_failed error=%r", exc)
            self._activate_fallback("is_seen_unexpected_error")
            return self._fallback.is_seen(url)

    def mark_seen(self, url: str) -> None:
        if self._repository is None:
            self._fallback.mark_seen(url)
            return

        try:
            self._repository.mark_seen(url)
        except sqlite3.Error as exc:
            logger.exception("event=dedup_db_write_failed error=%r", exc)
            self._activate_fallback("mark_seen_sqlite_error")
            self._fallback.mark_seen(url)
        except Exception as exc:
            logger.exception("event=dedup_db_write_failed error=%r", exc)
            self._activate_fallback("mark_seen_unexpected_error")
            self._fallback.mark_seen(url)


def create_link_dedup(db_path: Path | None = None) -> ResilientLinkDedup:
    """Initialize DB and return a resilient dedup store."""
    path = init_database(db_path)
    return ResilientLinkDedup(SeenLinkRepository(path))


def create_memory_link_dedup() -> ResilientLinkDedup:
    logger.warning("event=storage_fallback_in_memory reason='db_init_failed'")
    return ResilientLinkDedup(None)
