from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_client: Any | None = None


def redis_enabled() -> bool:
    return os.getenv("REDIS_ENABLED", "").strip().lower() in ("1", "true", "yes", "on")


def get_redis_optional(url: str | None = None) -> Any | None:
    global _client
    if not redis_enabled() and not url:
        return None
    if _client is not None:
        return _client
    redis_url = (url or os.getenv("REDIS_URL", "redis://localhost:6379/0")).strip()
    try:
        import redis.asyncio as redis

        _client = redis.from_url(redis_url, decode_responses=False)
        return _client
    except Exception:
        logger.exception("event=redis_client_init_failed url=%s", redis_url)
        return None


async def close_redis() -> None:
    global _client
    if _client is not None:
        try:
            await _client.close()
        except Exception:
            pass
        _client = None


async def cache_set(key: str, value: str, *, ttl_sec: int = 3600) -> bool:
    client = get_redis_optional()
    if client is None:
        return False
    try:
        await client.set(key, value.encode("utf-8"), ex=ttl_sec)
        return True
    except Exception:
        logger.exception("event=redis_cache_set_failed key=%s", key)
        return False


async def cache_get(key: str) -> str | None:
    client = get_redis_optional()
    if client is None:
        return None
    try:
        raw = await client.get(key)
        if raw is None:
            return None
        return raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
    except Exception:
        return None
