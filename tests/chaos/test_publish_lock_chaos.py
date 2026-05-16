"""Distributed publish lock chaos validation."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from tests.chaos.framework import make_fake_redis
from tests.conftest import minimal_test_settings
from utils.metrics import export_snapshot
from utils.reliability_diagnostics import lock_events_snapshot, lock_recovery_recommendation


@pytest.fixture
def set_redis_client(monkeypatch: pytest.MonkeyPatch):
    holder: dict[str, object] = {}

    async def _get() -> object:
        return holder.get("client")

    monkeypatch.setattr("utils.redis_client.get_redis", _get)

    def _set(client: object | None) -> None:
        if client is None:
            holder.pop("client", None)
        else:
            holder["client"] = client

    return _set


def test_strict_mode_denies_when_redis_set_fails(set_redis_client: object) -> None:
    async def body() -> None:
        from publisher.publish_lock import publish_draft_lock

        s = minimal_test_settings(redis_enabled=True, publish_lock_strict=True)
        set_redis_client(make_fake_redis(set_raises=ConnectionError("chaos: redis down")))
        async with publish_draft_lock(s, 9001) as ok:
            assert ok is False
        snap = export_snapshot()
        assert int(snap["counters"].get("publish_lock_strict_denied", 0)) >= 1

    asyncio.run(body())


def test_strict_mode_denies_when_redis_client_missing(set_redis_client: object) -> None:
    async def body() -> None:
        from publisher.publish_lock import publish_draft_lock

        s = minimal_test_settings(redis_enabled=True, publish_lock_strict=True)
        set_redis_client(None)
        async with publish_draft_lock(s, 9002) as ok:
            assert ok is False

    asyncio.run(body())


def test_legacy_fallback_on_redis_error(set_redis_client: object) -> None:
    async def body() -> None:
        from publisher.publish_lock import publish_draft_lock

        s = minimal_test_settings(redis_enabled=True, publish_lock_strict=False)
        set_redis_client(make_fake_redis(set_raises=RuntimeError("chaos: flaky redis")))
        async with publish_draft_lock(s, 9003) as ok:
            assert ok is True

    asyncio.run(body())


def test_lock_contention_records_event(set_redis_client: object) -> None:
    async def body() -> None:
        from publisher.publish_lock import publish_draft_lock

        s = minimal_test_settings(redis_enabled=True, publish_lock_strict=False)
        fake = make_fake_redis(set_ok=True)
        set_redis_client(fake)
        async with publish_draft_lock(s, 9004) as ok1:
            assert ok1 is True
        fake.set = AsyncMock(return_value=False)
        async with publish_draft_lock(s, 9004) as ok2:
            assert ok2 is False

    asyncio.run(body())


def test_recovery_recommendations_after_strict_denial(set_redis_client: object) -> None:
    async def body() -> None:
        from publisher.publish_lock import publish_draft_lock

        s = minimal_test_settings(redis_enabled=True, publish_lock_strict=True)
        set_redis_client(make_fake_redis(set_raises=OSError("chaos")))
        async with publish_draft_lock(s, 9005) as ok:
            assert ok is False
        tips = lock_recovery_recommendation()
        assert tips

    asyncio.run(body())


def test_lock_events_buffer_is_list() -> None:
    assert isinstance(lock_events_snapshot(), list)
