from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy import event, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from db.models import Base
from utils.database_url import is_postgresql_async_url, is_sqlite_async_url

logger = logging.getLogger(__name__)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _register_sqlite_pragmas(engine: Engine) -> None:
    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_conn: Any, connection_record: Any) -> None:
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA synchronous=NORMAL;")
        cursor.execute("PRAGMA busy_timeout=8000;")
        cursor.execute("PRAGMA foreign_keys=ON;")
        cursor.close()


def _migrate_sqlite_schema(connection: Connection) -> None:
    from sqlalchemy import inspect

    insp = inspect(connection)
    tables = insp.get_table_names()
    if "drafts" not in tables:
        return
    cols = {c["name"] for c in insp.get_columns("drafts")}
    if "content_hash" not in cols:
        connection.execute(
            text("ALTER TABLE drafts ADD COLUMN content_hash VARCHAR(64) NOT NULL DEFAULT '';"),
        )
        logger.info("SQLite migration: added drafts.content_hash")
        cols.add("content_hash")

    alters: list[tuple[str, str]] = [
        ("editor_title", "ALTER TABLE drafts ADD COLUMN editor_title TEXT"),
        ("editor_summary", "ALTER TABLE drafts ADD COLUMN editor_summary TEXT"),
        ("draft_extras", "ALTER TABLE drafts ADD COLUMN draft_extras TEXT NOT NULL DEFAULT '{}'"),
        ("edit_history", "ALTER TABLE drafts ADD COLUMN edit_history TEXT NOT NULL DEFAULT '[]'"),
        ("scheduled_publish_at", "ALTER TABLE drafts ADD COLUMN scheduled_publish_at TEXT"),
        ("publish_attempts", "ALTER TABLE drafts ADD COLUMN publish_attempts INTEGER NOT NULL DEFAULT 0"),
        ("last_publish_error", "ALTER TABLE drafts ADD COLUMN last_publish_error TEXT"),
        ("moderated_at", "ALTER TABLE drafts ADD COLUMN moderated_at TEXT"),
    ]
    for col_name, ddl in alters:
        if col_name not in cols:
            connection.execute(text(ddl))
            logger.info("SQLite migration: added drafts.%s", col_name)
            cols.add(col_name)


def get_engine() -> AsyncEngine:
    if _engine is None:
        raise RuntimeError("Database engine is not initialized")
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    if _session_factory is None:
        raise RuntimeError("Database session factory is not initialized")
    return _session_factory


def _engine_kwargs(database_url: str, pool_size: int, max_overflow: int) -> dict[str, Any]:
    connect_args: dict[str, object] = {}
    extra: dict[str, Any] = {}
    if is_sqlite_async_url(database_url):
        connect_args["check_same_thread"] = False
        connect_args["timeout"] = 30.0
        extra["connect_args"] = connect_args
    elif is_postgresql_async_url(database_url):
        extra["pool_size"] = pool_size
        extra["max_overflow"] = max_overflow
    return extra


async def init_db(
    database_url: str,
    *,
    pool_size: int = 5,
    max_overflow: int = 10,
) -> None:
    global _engine, _session_factory
    if _engine is not None:
        return

    kw = _engine_kwargs(database_url, pool_size, max_overflow)
    _engine = create_async_engine(
        database_url,
        echo=False,
        pool_pre_ping=True,
        **kw,
    )

    if is_sqlite_async_url(database_url):
        _register_sqlite_pragmas(_engine.sync_engine)

    _session_factory = async_sessionmaker(
        _engine,
        expire_on_commit=False,
        autoflush=False,
        close_resets_only=False,
    )

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        if is_sqlite_async_url(database_url):
            await conn.run_sync(_migrate_sqlite_schema)

    if is_sqlite_async_url(database_url):
        logger.info("Database initialized (SQLite WAL + busy timeout)")
    elif is_postgresql_async_url(database_url):
        logger.info("Database initialized (PostgreSQL async pool)")
    else:
        logger.info("Database initialized (%s)", database_url.split("://", 1)[0])


async def close_db() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
        logger.info("Database connections closed")


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
