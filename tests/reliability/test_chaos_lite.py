"""Chaos-lite — in-process failure injection (no K8s)."""

from __future__ import annotations

import asyncio
import pytest

from app.reliability.failed_draft_recovery import is_publish_failure_retryable
from db.reliability_repository import insert_pipeline_tick_start, mark_pipeline_tick_stale, find_stuck_pipeline_ticks
from app.ops.runtime.execution_lease import clear_stale_lease, try_acquire_lease, read_lease


def test_chaos_openai_timeout_classified_retryable() -> None:
    assert is_publish_failure_retryable(reason="APITimeoutError: request timed out") is True


def test_chaos_stale_tick_recovery(tmp_path, monkeypatch) -> None:
    import os
    import time

    async def _run() -> None:
        monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
        from app.config import load_settings
        from db.session import init_db, close_db

        s = load_settings()
        await init_db(s.database_url)
        try:
            await insert_pipeline_tick_start(tick_id="tick-chaos-1", node_name="test", correlation_id="c1")
            from datetime import datetime, timedelta, timezone
            from sqlalchemy import update
            from db.models import PipelineTick
            from db.session import session_scope

            old = datetime.now(timezone.utc) - timedelta(seconds=120)
            async with session_scope() as session:
                await session.execute(
                    update(PipelineTick)
                    .where(PipelineTick.tick_id == "tick-chaos-1")
                    .values(started_at=old)
                )
            row = await find_stuck_pipeline_ticks(older_than_sec=60.0)
            assert len(row) >= 1
            await mark_pipeline_tick_stale("tick-chaos-1", reason="chaos_test")
        finally:
            await close_db()

    asyncio.run(_run())


def test_chaos_stale_lease_takeover(tmp_path) -> None:
    rd = str(tmp_path)
    ok, _ = try_acquire_lease(rd, owner_id="a", runtime_id="r1", node_role="worker")
    assert ok
    path = tmp_path / "execution_lease.json"
    import json

    data = json.loads(path.read_text(encoding="utf-8"))
    data["heartbeat_unix"] = 1.0
    path.write_text(json.dumps(data), encoding="utf-8")
    assert clear_stale_lease(rd)
    ok2, _ = try_acquire_lease(rd, owner_id="b", runtime_id="r2", node_role="worker", force=False)
    assert ok2


def test_chaos_publish_timeout_classified() -> None:
    assert is_publish_failure_retryable(reason="Bot timeout") is True
