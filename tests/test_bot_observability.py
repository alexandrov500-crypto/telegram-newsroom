from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.observability.alerts import AlertManager, AlertSeverity
from bot.observability.health_server import create_health_app
from bot.observability.metrics import (
    ARTICLES_INGESTED,
    OPENAI_REQUESTS,
    record_article_ingested,
    record_openai_usage,
)
from bot.observability.registry import ObservabilityRegistry
from bot.observability.watchdog import BurnInWatchdog
from bot.storage.db import init_database
from bot.storage.observability_repository import ObservabilityRepository


@pytest.fixture
def registry() -> ObservabilityRegistry:
    reg = ObservabilityRegistry(scheduler_running=True, openai_available=True)
    reg.set_queue_backlog_provider(lambda: 3)
    return reg


def test_prometheus_metrics_increment() -> None:
    before = ARTICLES_INGESTED.labels(source="test")._value.get()
    record_article_ingested(source="test")
    after = ARTICLES_INGESTED.labels(source="test")._value.get()
    assert after == before + 1


def test_openai_usage_metrics() -> None:
    before = OPENAI_REQUESTS.labels(
        operation="summarization",
        model="gpt-test",
        status="success",
    )._value.get()
    record_openai_usage(
        operation="summarization",
        model="gpt-test",
        prompt_tokens=100,
        completion_tokens=20,
        success=True,
        cost_usd=0.001,
    )
    after = OPENAI_REQUESTS.labels(
        operation="summarization",
        model="gpt-test",
        status="success",
    )._value.get()
    assert after == before + 1


def test_health_endpoints(registry: ObservabilityRegistry) -> None:
    pytest.importorskip("fastapi")
    from httpx import ASGITransport, AsyncClient

    async def run() -> None:
        app = create_health_app(registry)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            health = await client.get("/health")
            assert health.status_code == 200
            assert health.json()["status"] == "ok"

            ready = await client.get("/ready")
            assert ready.status_code == 200
            body = ready.json()
            assert body["queue_backlog"] == 3

            metrics = await client.get("/metrics")
            assert metrics.status_code == 200
            assert "articles_ingested_total" in metrics.text

    asyncio.run(run())


def test_alert_deduplication_cooldown() -> None:
    async def run() -> None:
        bot = MagicMock()
        bot.send_message = AsyncMock()
        alerts = AlertManager(bot, chat_id=12345, cooldown_sec=60)
        first = await alerts.critical("Publisher crashed", details={"x": 1})
        second = await alerts.critical("Publisher crashed", details={"x": 2})
        assert first is True
        assert second is False
        assert bot.send_message.await_count == 1

    asyncio.run(run())


def test_observability_repository_persist_and_aggregate(tmp_path: Path) -> None:
    db_path = init_database(tmp_path / "obs.db")
    repo = ObservabilityRepository(db_path)
    repo.record_openai_event(
        operation="summarization",
        model="gpt-4.1-mini",
        prompt_tokens=100,
        completion_tokens=50,
        cost_usd=0.01,
        latency_ms=200,
        success=True,
    )
    repo.aggregate_daily()
    daily = repo.get_daily()
    assert daily is not None
    assert daily.request_count >= 1
    assert daily.cost_usd >= 0.01


def test_watchdog_probe_does_not_raise(registry: ObservabilityRegistry) -> None:
    async def run() -> None:
        watchdog = BurnInWatchdog(registry, alerts=None, interval_sec=1)
        await watchdog._probe_once()

    asyncio.run(run())
