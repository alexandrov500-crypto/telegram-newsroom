from __future__ import annotations

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

from scheduler.jobs import build_pipeline_context, run_pipeline
from scheduler.pipeline_lock import get_pipeline_lock
from scheduler.runtime_context import set_pipeline_context
from tests.conftest import minimal_test_settings
from utils.metrics import export_snapshot, inc, reset_metrics


@pytest.fixture(autouse=True)
def _metrics_and_context_cleanup():
    reset_metrics()
    set_pipeline_context(None)
    yield
    reset_metrics()
    set_pipeline_context(None)


@pytest.fixture
def sqlite_file_db(tmp_path):
    async def setup() -> str:
        from db.session import close_db, init_db

        await close_db()
        url = f"sqlite+aiosqlite:///{tmp_path / 'scheduler_integration.db'}"
        await init_db(url)
        return url

    url = asyncio.run(setup())
    yield url

    async def teardown() -> None:
        from db.session import close_db

        await close_db()

    asyncio.run(teardown())


def test_run_pipeline_single_tick_orchestration(monkeypatch, sqlite_file_db):
    async def body() -> None:
        settings = minimal_test_settings(database_url=sqlite_file_db)
        bot = MagicMock()
        bot.session = MagicMock()
        bot.session.close = AsyncMock()
        openai = MagicMock()
        openai.close = AsyncMock()

        ctx = build_pipeline_context(settings, bot, openai)

        async def fake_collect(c):
            c.tick_timings["collect_sec"] = 0.01
            inc("posts_collected", 2)
            inc("openai_retries", 1)

        async def fake_summarize(c):
            c.tick_timings["db_fetch_unprocessed_sec"] = 0.001
            c.tick_timings["cluster_sec"] = 0.0
            c.last_cluster_size = 0

        monkeypatch.setattr("scheduler.jobs._collect_step", fake_collect)
        monkeypatch.setattr("scheduler.jobs._summarize_step", fake_summarize)

        lock = get_pipeline_lock()
        assert not lock.locked()

        await run_pipeline(ctx)

        assert not lock.locked()
        assert not ctx.tick_in_progress
        assert "collect_sec" in ctx.tick_timings
        assert ctx.last_scheduler_wall_sec > 0

        snap = export_snapshot()
        assert snap["counters"]["posts_collected"] == 2
        assert snap["counters"]["openai_retries"] == 1
        assert snap["pipeline_duration_sample_count"] >= 1

    asyncio.run(body())


def test_run_pipeline_inner_failure_releases_lock_and_logs(monkeypatch, sqlite_file_db, caplog):
    caplog.set_level(logging.ERROR)

    async def body() -> None:
        settings = minimal_test_settings(database_url=sqlite_file_db)
        bot = MagicMock()
        bot.session = MagicMock()
        bot.session.close = AsyncMock()
        openai = MagicMock()
        openai.close = AsyncMock()
        ctx = build_pipeline_context(settings, bot, openai)

        async def fake_collect(c):
            c.tick_timings["collect_sec"] = 0.005

        async def boom_summarize(_c):
            raise RuntimeError("deterministic summarizer failure")

        monkeypatch.setattr("scheduler.jobs._collect_step", fake_collect)
        monkeypatch.setattr("scheduler.jobs._summarize_step", boom_summarize)

        lock = get_pipeline_lock()
        await run_pipeline(ctx)

        assert not lock.locked()
        assert not ctx.tick_in_progress
        assert ctx.last_scheduler_wall_sec > 0
        assert export_snapshot()["pipeline_duration_sample_count"] >= 1

    asyncio.run(body())
    assert "deterministic summarizer failure" in caplog.text
