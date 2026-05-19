from __future__ import annotations

import os
import sqlite3
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class NewsroomRepositoryBackend(ABC):
    """Storage abstraction for SQLite → Postgres migration."""

    @abstractmethod
    def ping(self) -> bool:
        ...

    @abstractmethod
    def backend_name(self) -> str:
        ...


class SqliteNewsroomBackend(NewsroomRepositoryBackend):
    def __init__(self, db_path: Path) -> None:
        self._path = db_path

    def ping(self) -> bool:
        try:
            with sqlite3.connect(self._path, timeout=3) as conn:
                conn.execute("SELECT 1")
            return True
        except Exception:
            return False

    def backend_name(self) -> str:
        return "sqlite"


class PostgresNewsroomBackend(NewsroomRepositoryBackend):
    def __init__(self, database_url: str) -> None:
        self._url = database_url.replace("postgresql+asyncpg://", "postgresql://")

    def ping(self) -> bool:
        try:
            import psycopg

            with psycopg.connect(self._url, connect_timeout=4) as conn:
                conn.execute("SELECT 1")
            return True
        except Exception:
            return False

    def backend_name(self) -> str:
        return "postgres"


class RedisQueueBackend:
    """Redis-backed queue, distributed lock, and idempotency cache (feature-flagged)."""

    def __init__(self, redis_url: str) -> None:
        self._url = redis_url
        self._client: Any | None = None

    def connect(self) -> bool:
        try:
            import redis

            self._client = redis.from_url(self._url, socket_connect_timeout=3)
            self._client.ping()
            return True
        except Exception:
            self._client = None
            return False

    def queue_depth(self, queue_name: str) -> int:
        if self._client is None:
            return 0
        try:
            return int(self._client.llen(queue_name))
        except Exception:
            return 0

    def acquire_lock(self, key: str, *, ttl_sec: int = 30) -> bool:
        if self._client is None:
            return True
        try:
            return bool(self._client.set(key, "1", nx=True, ex=ttl_sec))
        except Exception:
            return False

    def release_lock(self, key: str) -> None:
        if self._client is None:
            return
        try:
            self._client.delete(key)
        except Exception:
            pass

    def idempotency_seen(self, key: str, *, ttl_sec: int = 86400) -> bool:
        """Return True if key already processed (SET NX semantics)."""
        if self._client is None:
            return False
        try:
            return not bool(self._client.set(f"idemp:{key}", "1", nx=True, ex=ttl_sec))
        except Exception:
            return False

    def enqueue_retry(self, queue_name: str, payload: str) -> bool:
        if self._client is None:
            return False
        try:
            self._client.rpush(queue_name, payload)
            return True
        except Exception:
            return False


def resolve_storage_stack(db_path: Path) -> dict[str, Any]:
    url = os.getenv("DATABASE_URL", "").strip()
    use_pg = os.getenv("NEWSROOM_USE_POSTGRES", "").lower() in ("1", "true", "yes")
    use_redis = os.getenv("REDIS_ENABLED", "").lower() in ("1", "true", "yes")
    primary: NewsroomRepositoryBackend = SqliteNewsroomBackend(db_path)
    if use_pg and url and "postgresql" in url:
        primary = PostgresNewsroomBackend(url)
    redis: RedisQueueBackend | None = None
    if use_redis:
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        redis = RedisQueueBackend(redis_url)
        redis.connect()
    dual_write = os.getenv("NEWSROOM_DUAL_WRITE", "").lower() in ("1", "true", "yes")
    return {
        "primary": primary,
        "sqlite_fallback": SqliteNewsroomBackend(db_path),
        "redis": redis,
        "dual_write": dual_write,
        "primary_ok": primary.ping(),
    }
