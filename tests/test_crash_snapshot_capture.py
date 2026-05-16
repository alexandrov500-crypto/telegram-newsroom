from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from scheduler.jobs import build_pipeline_context, run_pipeline
from scheduler.runtime_context import set_pipeline_context
from tests.conftest import minimal_test_settings
from utils.runtime_state_store import load_latest_runtime_snapshot, snapshot_dir


@pytest.fixture(autouse=True)
def _ctx():
    set_pipeline_context(None)
    yield
    set_pipeline_context(None)


def test_pipeline_failure_persists_snapshot(tmp_path, monkeypatch):
    async def body() -> None:
        from db.session import close_db, init_db

        dbfile = tmp_path / "crash.db"
        url = f"sqlite+aiosqlite:///{dbfile}"
        await close_db()
        await init_db(url)
        s = minimal_test_settings(
            database_url=url,
            runtime_state_dir=str(tmp_path / "snap"),
            runtime_snapshots_max_count=10,
        )
        bot = MagicMock()
        bot.session = MagicMock()
        bot.session.close = AsyncMock()
        openai = MagicMock()
        openai.close = AsyncMock()
        ctx = build_pipeline_context(s, bot, openai)

        async def ok_collect(c):
            c.tick_timings["collect_sec"] = 0.001

        async def boom(_c):
            raise RuntimeError("boom_tick")

        monkeypatch.setattr("scheduler.jobs._collect_step", ok_collect)
        monkeypatch.setattr("scheduler.jobs._summarize_step", boom)
        monkeypatch.setattr("scheduler.jobs.maybe_flush_runtime_events_to_snapshot", lambda _s: None)

        await run_pipeline(ctx)
        await close_db()

    asyncio.run(body())

    s2 = minimal_test_settings(runtime_state_dir=str(tmp_path / "snap"))
    assert any(snapshot_dir(s2).glob("snapshot_*.json"))
    data = load_latest_runtime_snapshot(s2)
    assert data is not None
    assert data.get("reason") == "pipeline_inner_failed"
