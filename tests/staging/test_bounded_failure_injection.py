"""Bounded failure-injection proxies for staging sign-off (CI-safe, no Telegram API)."""

from __future__ import annotations

import asyncio

import pytest

from tests.chaos.framework import RecordingRetryTransport, make_fake_redis
from tests.conftest import minimal_test_settings
from utils.metrics import export_snapshot, reset_metrics
from workers.base import WorkerRole
from workers.dispatcher import HandlerRegistry
from workers.retry import build_policy_from_settings
from workers.runtime import WorkerRuntime
from worker.job_queue import JobEnvelope, JobKind, JobRetryMeta


@pytest.fixture(autouse=True)
def _reset_metrics() -> None:
    reset_metrics()
    yield
    reset_metrics()


def test_redis_unavailable_strict_denies_second_publish(monkeypatch: pytest.MonkeyPatch) -> None:
    async def body() -> None:
        from publisher.publish_lock import publish_draft_lock

        async def get_redis() -> None:
            return None

        monkeypatch.setattr("utils.redis_client.get_redis", get_redis)
        s = minimal_test_settings(redis_enabled=True, publish_lock_strict=True)
        async with publish_draft_lock(s, 88001) as ok:
            assert ok is False
        snap = export_snapshot()
        assert int(snap["counters"].get("publish_lock_strict_denied", 0)) >= 1

    asyncio.run(body())


def test_redis_contention_no_duplicate_lock_holder(monkeypatch: pytest.MonkeyPatch) -> None:
    from unittest.mock import AsyncMock

    async def body() -> None:
        from publisher.publish_lock import publish_draft_lock

        holder: dict[str, object] = {}

        async def get_redis() -> object:
            return holder.get("client")

        monkeypatch.setattr("utils.redis_client.get_redis", get_redis)
        fake = make_fake_redis(set_ok=True)
        holder["client"] = fake
        s = minimal_test_settings(redis_enabled=True, publish_lock_strict=False)
        async with publish_draft_lock(s, 88002) as ok1:
            assert ok1 is True
        fake.set = AsyncMock(return_value=False)
        async with publish_draft_lock(s, 88002) as ok2:
            assert ok2 is False
        snap = export_snapshot()
        assert int(snap["counters"].get("publish_lock_contention", 0)) >= 1

    asyncio.run(body())


def test_forced_reconnect_increments_metric() -> None:
    from unittest.mock import AsyncMock, MagicMock

    from collector.retry import ensure_connected

    async def body() -> None:
        client = MagicMock()
        client.is_connected.return_value = False
        client.connect = AsyncMock()
        await ensure_connected(client)
        assert int(export_snapshot()["counters"]["telethon_reconnects"]) >= 1

    asyncio.run(body())


def test_publish_retry_increments_counter() -> None:
    from publisher.retry import async_retry

    async def body() -> None:
        n = 0

        async def flaky() -> int:
            nonlocal n
            n += 1
            if n < 2:
                raise RuntimeError("injected")
            return 1

        assert await async_retry(flaky, attempts=3, delay_sec=0.0, label="inj") == 1
        assert int(export_snapshot()["counters"]["publish_retries"]) >= 1

    asyncio.run(body())


def test_worker_restart_safe_retry_order() -> None:
    async def body() -> None:
        s = minimal_test_settings(worker_retry_safe=True, openai_json_max_retries=1)
        rt = WorkerRuntime(s, role=WorkerRole.INGEST, job_kind=JobKind.INGEST, registry=HandlerRegistry())
        transport = RecordingRetryTransport()
        env = JobEnvelope(JobKind.INGEST, {"job_type": "INGEST_ARTICLE"}, retry=JobRetryMeta(attempt=0))
        policy = build_policy_from_settings(s, envelope_attempt=0)
        await rt._handle_failure(
            transport,
            "{}",
            env,
            "staging-inj-1",
            RuntimeError("injected"),
            0,
            policy,
        )
        assert transport.order == ["enqueue", "ack"]

    asyncio.run(body())
