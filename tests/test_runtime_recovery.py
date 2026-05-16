from __future__ import annotations

import asyncio
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
        url = f"sqlite+aiosqlite:///{tmp_path / 'recovery.db'}"
        await init_db(url)
        return url

    url = asyncio.run(setup())
    yield url

    async def teardown() -> None:
        from db.session import close_db

        await close_db()

    asyncio.run(teardown())


def _run_ticks(monkeypatch, sqlite_file_db, collect_impl, summarize_impl, n_ticks: int = 3) -> None:
    async def body() -> None:
        settings = minimal_test_settings(database_url=sqlite_file_db)
        bot = MagicMock()
        bot.session = MagicMock()
        bot.session.close = AsyncMock()
        openai = MagicMock()
        openai.close = AsyncMock()
        ctx = build_pipeline_context(settings, bot, openai)

        monkeypatch.setattr("scheduler.jobs._collect_step", collect_impl)
        monkeypatch.setattr("scheduler.jobs._summarize_step", summarize_impl)

        for _ in range(n_ticks):
            await run_pipeline(ctx)
            assert not get_pipeline_lock().locked()
            assert not ctx.tick_in_progress

    asyncio.run(body())


def test_recovery_after_summarize_failure_then_success(monkeypatch, sqlite_file_db):
    state = {"fail": True}

    async def collect_ok(c):
        c.tick_timings["collect_sec"] = 0.001
        inc("posts_collected", 1)

    async def summarize_toggle(c):
        c.tick_timings["db_fetch_unprocessed_sec"] = 0.001
        c.last_cluster_size = 0
        if state["fail"]:
            state["fail"] = False
            raise RuntimeError("summarize deterministic failure")

    _run_ticks(monkeypatch, sqlite_file_db, collect_ok, summarize_toggle, n_ticks=2)

    snap = export_snapshot()
    assert snap["pipeline_duration_sample_count"] >= 2
    assert snap["counters"]["posts_collected"] == 2


def test_recovery_after_collector_failure(monkeypatch, sqlite_file_db):
    async def collect_fail(_c):
        raise OSError(5, "collector deterministic")

    async def summarize_ok(c):
        c.tick_timings["db_fetch_unprocessed_sec"] = 0.001
        c.last_cluster_size = 0

    _run_ticks(monkeypatch, sqlite_file_db, collect_fail, summarize_ok, n_ticks=1)
    assert export_snapshot()["pipeline_duration_sample_count"] >= 1


def test_recovery_after_db_step_failure(monkeypatch, sqlite_file_db):
    async def collect_ok(c):
        c.tick_timings["collect_sec"] = 0.001

    async def summarize_db_fail(_c):
        import sqlalchemy.exc as sa_exc

        raise sa_exc.OperationalError("stmt", {}, Exception("db down"))

    _run_ticks(monkeypatch, sqlite_file_db, collect_ok, summarize_db_fail, n_ticks=1)
    assert not get_pipeline_lock().locked()


def test_repeated_ticks_deterministic_metrics_progression(monkeypatch, sqlite_file_db):
    tick = {"n": 0}

    async def collect_incr(c):
        c.tick_timings["collect_sec"] = 0.001
        tick["n"] += 1
        inc("posts_collected", 1)

    async def summarize_ok(c):
        c.tick_timings["db_fetch_unprocessed_sec"] = 0.001
        c.last_cluster_size = 0

    _run_ticks(monkeypatch, sqlite_file_db, collect_incr, summarize_ok, n_ticks=4)
    assert export_snapshot()["counters"]["posts_collected"] == 4
