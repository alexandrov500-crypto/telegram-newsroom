"""Optional Redis async client (singleton). Disabled → all helpers no-op / None."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_client: Any = None


def reset_redis_client_for_tests() -> None:
    global _client
    _client = None


def redis_client_active() -> bool:
    return _client is not None


async def init_redis_from_settings(settings: Any) -> None:
    """Connect when REDIS_ENABLED; idempotent."""
    global _client
    if _client is not None:
        return
    if not bool(getattr(settings, "redis_enabled", False)):
        return
    url = str(getattr(settings, "redis_url", "") or "").strip()
    if not url:
        logger.warning("redis.init_skipped: empty REDIS_URL")
        return
    try:
        from redis.asyncio import Redis

        _client = Redis.from_url(url, decode_responses=True, health_check_interval=30)
        await _client.ping()
        logger.info("redis.connected host=%s", _safe_host_hint(url))
    except Exception as exc:
        _client = None
        try:
            from utils.redis_transport_metrics import record_redis_connect_failure

            record_redis_connect_failure()
        except Exception:
            pass
        logger.warning("redis.connect_failed degraded_without_redis error=%s", repr(exc))


def _safe_host_hint(url: str) -> str:
    try:
        return urlparse(url).hostname or "default"
    except Exception:
        return "unparsed"


async def get_redis() -> Any | None:
    return _client


async def redis_ping_ok() -> bool | None:
    """
    None = Redis not configured.
    True/False = ping result.
    """
    if _client is None:
        return None
    try:
        await _client.ping()
        return True
    except Exception:
        return False


async def close_redis() -> None:
    global _client
    if _client is None:
        return
    try:
        await _client.aclose()
    except Exception as exc:
        logger.warning("redis.close_failed error=%s", repr(exc))
    finally:
        _client = None
        logger.info("redis.closed")


async def reconnect_redis(settings: Any) -> bool:
    """
    Close and re-open the singleton client (operational recovery / tests).
    Returns True if a client is active after the attempt.
    """
    try:
        from utils.redis_transport_metrics import begin_reconnect_cycle, end_reconnect_cycle

        begin_reconnect_cycle()
    except Exception:
        pass
    await close_redis()
    await init_redis_from_settings(settings)
    ok = redis_client_active()
    try:
        from utils.redis_transport_metrics import end_reconnect_cycle

        end_reconnect_cycle()
    except Exception:
        pass
    return ok
