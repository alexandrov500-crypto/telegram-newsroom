"""Phase 2 self-healing: ticks, retry classification, correlation."""

from __future__ import annotations

import pytest

from app.reliability.failed_draft_recovery import is_publish_failure_retryable
from utils.operational_context import begin_pipeline_tick, correlation_fields_for_draft, reset_correlation_id, reset_tick_id


def test_begin_pipeline_tick_sets_correlation() -> None:
    tid, ttok, ctok = begin_pipeline_tick()
    try:
        fields = correlation_fields_for_draft()
        assert fields.get("correlation_id") == tid
        assert fields.get("tick_id") == tid
    finally:
        reset_tick_id(ttok)
        reset_correlation_id(ctok)


@pytest.mark.parametrize(
    ("reason", "expected"),
    [
        ("Telegram network timeout", True),
        ("desk_reject:quality_below_threshold", False),
        ("duplicate publish blocked", False),
        ("sqlite database is locked", True),
    ],
)
def test_retryable_classification(reason: str, expected: bool) -> None:
    assert is_publish_failure_retryable(reason=reason) is expected


def test_pipeline_tick_persist(tmp_path, monkeypatch) -> None:
    import asyncio

    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 't.db'}")
    from app.config import load_settings
    from db.session import init_db, close_db
    from db.reliability_repository import insert_pipeline_tick_start, complete_pipeline_tick, latest_pipeline_tick

    async def _run() -> None:
        settings = load_settings()
        await init_db(settings.database_url)
        try:
            await insert_pipeline_tick_start(tick_id="tick-test-1", node_name="pytest", correlation_id="tick-test-1")
            await complete_pipeline_tick("tick-test-1", drafts_created=1, posts_collected=3, status="ok")
            row = await latest_pipeline_tick()
            assert row is not None
            assert row.tick_id == "tick-test-1"
            assert row.status == "ok"
            assert row.drafts_created == 1
        finally:
            await close_db()

    asyncio.run(_run())
