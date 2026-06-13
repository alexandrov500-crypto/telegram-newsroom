"""Tests for wire backlog drain and recovery mode."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from db.session import close_db, init_db, session_scope


@pytest.fixture(autouse=True)
def _news_beat(monkeypatch):
    monkeypatch.setenv("NEWSROOM_CHANNEL_BEAT", "top_news")
    monkeypatch.setenv("WIRE_RECOVERY_ENABLED", "true")
    monkeypatch.setenv("WIRE_BACKLOG_FRESH_FIRST", "true")


def test_wire_throughput_recovery_on_silence(monkeypatch):
    from app.editorial import wire_recovery

    monkeypatch.setattr(wire_recovery, "minutes_since_last_publish", lambda: 60.0)
    assert wire_recovery.wire_throughput_recovery_active(silence_min=60.0) is True


def test_wire_throughput_recovery_on_backlog(monkeypatch):
    from app.editorial import wire_recovery

    monkeypatch.setattr(wire_recovery, "minutes_since_last_publish", lambda: 5.0)
    assert wire_recovery.wire_throughput_recovery_active(backlog=500, silence_min=5.0) is True
    assert wire_recovery.wire_throughput_recovery_active(backlog=100, silence_min=5.0) is False


def test_apply_cooldowns_bypassed_in_wire_recovery(monkeypatch, tmp_path):
    from editorial.governance.diversity_controls import apply_cooldowns

    monkeypatch.setenv("WIRE_BYPASS_SOURCE_COOLDOWN", "true")
    with patch("app.editorial.wire_recovery.wire_bypass_diversity_cooldowns", return_value=True):
        blocked, codes = apply_cooldowns(
            str(tmp_path),
            topic_key="macro",
            channels=["@banksta"],
            source_cap=1,
            cooldown_sec=3600.0,
        )
    assert blocked is False
    assert codes == []


def test_fetch_wire_unprocessed_posts_newest_first(tmp_path, monkeypatch) -> None:
    from app.editorial.wire_backlog import fetch_wire_unprocessed_posts
    from db.models import RawPost

    url = f"sqlite+aiosqlite:///{tmp_path / 'wire.db'}"

    async def body() -> None:
        await close_db()
        await init_db(url)
        try:
            now = datetime.now(UTC)
            async with session_scope() as session:
                session.add_all(
                    [
                        RawPost(
                            channel_name="old_src",
                            message_id=1,
                            text="old wire",
                            created_at=now - timedelta(hours=2),
                            collected_at=now - timedelta(hours=2),
                        ),
                        RawPost(
                            channel_name="banksta",
                            message_id=2,
                            text="fresh wire",
                            created_at=now - timedelta(minutes=5),
                            collected_at=now - timedelta(minutes=5),
                        ),
                    ]
                )
                await session.commit()
            async with session_scope() as session:
                rows = await fetch_wire_unprocessed_posts(session, limit=10)
            assert len(rows) >= 2
            assert int(rows[0].message_id) == 2
        finally:
            await close_db()

    asyncio.run(body())


def test_skip_stale_wire_backlog(tmp_path, monkeypatch) -> None:
    from app.editorial.wire_backlog import skip_stale_wire_backlog
    from db.models import RawPost

    monkeypatch.setenv("WIRE_STALE_SKIP_HOURS", "24")
    url = f"sqlite+aiosqlite:///{tmp_path / 'stale.db'}"

    async def body() -> None:
        await close_db()
        await init_db(url)
        try:
            now = datetime.now(UTC)
            async with session_scope() as session:
                stale = RawPost(
                    channel_name="stale",
                    message_id=99,
                    text="ancient",
                    created_at=now - timedelta(hours=48),
                    collected_at=now - timedelta(hours=48),
                )
                session.add(stale)
                await session.commit()
                stale_id = int(stale.id)
            async with session_scope() as session:
                n = await skip_stale_wire_backlog(session)
                assert n == 1
            async with session_scope() as session:
                row = await session.get(RawPost, stale_id)
                assert row is not None
                assert row.processed_at is not None
        finally:
            await close_db()

    asyncio.run(body())
