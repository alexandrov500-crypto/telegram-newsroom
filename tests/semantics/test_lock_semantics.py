"""Publish lock semantics verification."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from tests.chaos.framework import make_fake_redis
from tests.conftest import minimal_test_settings


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


def test_strict_denies_without_redis(set_redis_client) -> None:
    async def body() -> None:
        from publisher.publish_lock import publish_draft_lock

        s = minimal_test_settings(redis_enabled=True, publish_lock_strict=True)
        set_redis_client(None)
        async with publish_draft_lock(s, 42) as ok:
            assert ok is False

    asyncio.run(body())


def test_contention_yields_false(set_redis_client) -> None:
    async def body() -> None:
        from publisher.publish_lock import publish_draft_lock

        s = minimal_test_settings(redis_enabled=True, publish_lock_strict=False)
        fake = make_fake_redis(set_ok=True)
        set_redis_client(fake)
        async with publish_draft_lock(s, 99) as ok1:
            assert ok1 is True
        fake.set = AsyncMock(return_value=False)
        async with publish_draft_lock(s, 99) as ok2:
            assert ok2 is False

    asyncio.run(body())
