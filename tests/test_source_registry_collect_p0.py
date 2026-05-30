"""P0 collector: registry expand flag, broken sources, partial commit."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

import pytest

from app.sources.registry import (
    BROKEN_REGISTRY_HANDLES,
    deactivate_broken_registry_sources,
    load_active_source_handles,
    seed_registry_if_empty,
)
from collector.progress import CollectProgress
from collector.service import _commit_after_channel, collect_all_channels
from db.models import SourceRegistryEntry
from db.session import close_db, init_db, session_scope
from tests.conftest import minimal_test_settings


def test_load_active_source_handles_expand_false_env_only() -> None:
    url = "sqlite+aiosqlite:///:memory:"

    async def body() -> None:
        await init_db(url)
        try:
            settings = minimal_test_settings(
                source_channels=("@cb_economics", "@tnews365", "@DeCenter"),
                source_registry_expand=False,
            )
            now = datetime.now(UTC)
            async with session_scope() as session:
                session.add(
                    SourceRegistryEntry(
                        handle="bloomberg",
                        tier="T0",
                        vertical="corporate",
                        poll_interval_sec=300,
                        trust_score=0.9,
                        status="active",
                        extras_json="{}",
                        created_at=now,
                        updated_at=now,
                    )
                )
            handles = await load_active_source_handles(settings)
            assert handles == ["@cb_economics", "@decenter", "@tnews365"]
        finally:
            await close_db()

    asyncio.run(body())


def test_load_active_source_handles_expand_true_merges_registry() -> None:
    url = "sqlite+aiosqlite:///:memory:"

    async def body() -> None:
        await init_db(url)
        try:
            settings = minimal_test_settings(
                source_channels=("@cb_economics",),
                source_registry_expand=True,
            )
            now = datetime.now(UTC)
            async with session_scope() as session:
                session.add(
                    SourceRegistryEntry(
                        handle="bloomberg",
                        tier="T0",
                        vertical="corporate",
                        poll_interval_sec=300,
                        trust_score=0.9,
                        status="active",
                        extras_json="{}",
                        created_at=now,
                        updated_at=now,
                    )
                )
            handles = await load_active_source_handles(settings)
            assert handles == ["@bloomberg", "@cb_economics"]
        finally:
            await close_db()

    asyncio.run(body())


def test_deactivate_broken_registry_sources_idempotent() -> None:
    url = "sqlite+aiosqlite:///:memory:"

    async def body() -> None:
        await init_db(url)
        try:
            now = datetime.now(UTC)
            async with session_scope() as session:
                for handle in BROKEN_REGISTRY_HANDLES:
                    session.add(
                        SourceRegistryEntry(
                            handle=handle,
                            tier="T0",
                            vertical="corporate",
                            poll_interval_sec=300,
                            trust_score=0.5,
                            status="active",
                            extras_json="{}",
                            created_at=now,
                            updated_at=now,
                        )
                    )
            first = await deactivate_broken_registry_sources()
            second = await deactivate_broken_registry_sources()
            assert first == len(BROKEN_REGISTRY_HANDLES)
            assert second == 0
            async with session_scope() as session:
                from sqlalchemy import select

                rows = list((await session.execute(select(SourceRegistryEntry))).scalars())
            assert all(r.status == "inactive" for r in rows)
            reuters = next(r for r in rows if r.handle == "reutersbiz")
            assert json.loads(reuters.extras_json).get("deactivated_reason") == "broken_telegram_handle_p0"
        finally:
            await close_db()

    asyncio.run(body())


def test_seed_registry_marks_broken_handles_inactive() -> None:
    url = "sqlite+aiosqlite:///:memory:"

    async def body() -> None:
        await init_db(url)
        try:
            inserted = await seed_registry_if_empty()
            assert inserted == 25
            async with session_scope() as session:
                from sqlalchemy import select

                rows = {r.handle: r for r in (await session.execute(select(SourceRegistryEntry))).scalars()}
            for handle in BROKEN_REGISTRY_HANDLES:
                assert rows[handle].status == "inactive"
            assert rows["cb_economics"].status == "active"
        finally:
            await close_db()

    asyncio.run(body())


def test_per_channel_commit_invoked(monkeypatch: pytest.MonkeyPatch) -> None:
    commit_calls: list[str] = []

    async def fake_collect(_client, _session, *, channel, **_kwargs) -> int:
        return 1 if channel == "@a" else 0

    async def counting_commit(session, *, channel, new_rows, progress) -> None:
        await session.commit()
        commit_calls.append(channel)
        if progress is not None:
            progress.record_channel(channel, new_rows)

    monkeypatch.setattr("collector.service.collect_channel_messages", fake_collect)
    monkeypatch.setattr("collector.service._commit_after_channel", counting_commit)

    class _Session:
        async def commit(self) -> None:
            return None

    async def body() -> None:
        progress = CollectProgress()
        progress.planned_total = 2
        total = await collect_all_channels(
            client=object(),  # type: ignore[arg-type]
            session=_Session(),  # type: ignore[arg-type]
            channels=["@a", "@b"],
            limit_per_channel=5,
            telethon_max_attempts=1,
            channel_delay_seconds=0,
            progress=progress,
        )
        assert total == 1
        assert commit_calls == ["@a", "@b"]
        assert progress.new_rows_total == 1
        assert progress.channels_processed == 2

    asyncio.run(body())


def test_commit_after_channel_logs_partial(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[str] = []

    def fake_log_event(_logger, event, **kwargs) -> None:
        events.append(event)

    monkeypatch.setattr("collector.progress.log_event", fake_log_event)

    class _Session:
        async def commit(self) -> None:
            return None

    async def body() -> None:
        progress = CollectProgress()
        progress.planned_total = 1
        await _commit_after_channel(_Session(), channel="@cb_economics", new_rows=2, progress=progress)
        assert "collector.channels_processed" in events
        assert "collector.partial_commit" in events
        assert progress.new_rows_total == 2

    asyncio.run(body())


def test_collect_progress_channels_skipped() -> None:
    progress = CollectProgress(planned_total=5)
    progress.record_channel("@a", 0)
    progress.record_channel("@b", 1)
    assert progress.channels_skipped_count() == 3
