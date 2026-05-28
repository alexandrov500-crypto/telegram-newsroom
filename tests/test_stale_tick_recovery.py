"""Stale pipeline tick finalization."""

from __future__ import annotations

import asyncio

import pytest

from db.reliability_repository import finalize_stale_pipeline_tick, insert_pipeline_tick_start
from db.session import close_db, init_db


def test_finalize_stale_tick_idempotent(tmp_path) -> None:
    url = f"sqlite+aiosqlite:///{tmp_path / 'stale_ticks.db'}"

    async def run() -> None:
        await close_db()
        await init_db(url)
        await insert_pipeline_tick_start(tick_id="tick-stale-1", node_name="test")
        ok1 = await finalize_stale_pipeline_tick("tick-stale-1", terminal_reason="stale_tick_timeout")
        assert ok1 is True
        ok2 = await finalize_stale_pipeline_tick("tick-stale-1")
        assert ok2 is False
        await close_db()

    asyncio.run(run())

    import sqlite3
    from utils.database_url import sqlite_path_from_url

    path = sqlite_path_from_url(url)
    row = sqlite3.connect(path).execute(
        "SELECT status, detail_json, finished_at FROM pipeline_ticks WHERE tick_id='tick-stale-1'"
    ).fetchone()
    assert row[0] == "reject"
    assert "committed_reject" in row[1]
    assert "stale_tick_timeout" in row[1]
    assert row[2] is not None
