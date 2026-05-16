from __future__ import annotations

import asyncio

import pytest

from db import repository as repo
from db.models import DraftStatus
from db.session import close_db, init_db, session_scope
from utils.metrics import reset_metrics, snapshot
from utils.text_hash import sha256_hex


def _run_with_db(url: str, coro) -> None:
    async def setup() -> None:
        await close_db()
        await init_db(url)

    asyncio.run(setup())
    try:
        asyncio.run(coro())
    finally:
        asyncio.run(close_db())


def test_create_list_approve_publish_flow(tmp_path) -> None:
    reset_metrics()
    url = f"sqlite+aiosqlite:///{tmp_path / 'draft_workflow.db'}"

    async def body() -> None:
        async with session_scope() as session:
            d = await repo.create_draft(
                session,
                content="c1",
                content_hash=sha256_hex("c1"),
                sources_payload=[{"channel": "@x", "message_id": 1}],
            )
            did = int(d.id)
        async with session_scope() as session:
            pending = await repo.list_pending_drafts(session, limit=10)
            assert [x.id for x in pending] == [did]
            assert await repo.approve_draft(session, did) is True
            assert await repo.approve_draft(session, did) is True
            assert await repo.mark_draft_publishing(session, did) is True
            assert await repo.mark_draft_publishing(session, did) is False
        async with session_scope() as session:
            assert await repo.mark_draft_published(session, did, telegram_post_id=999) is True
            assert await repo.mark_draft_published(session, did, telegram_post_id=999) is True
        assert snapshot()["drafts_created"] >= 1
        assert snapshot()["drafts_approved"] == 1
        assert snapshot()["drafts_published"] == 1

    _run_with_db(url, body)


def test_list_pending_ordering(tmp_path) -> None:
    url = f"sqlite+aiosqlite:///{tmp_path / 'draft_order.db'}"

    async def body() -> None:
        async with session_scope() as session:
            await repo.create_draft(
                session,
                content="first",
                content_hash=sha256_hex("first"),
                sources_payload=[{"channel": "@a", "message_id": 1}],
            )
            await repo.create_draft(
                session,
                content="second",
                content_hash=sha256_hex("second"),
                sources_payload=[{"channel": "@a", "message_id": 2}],
            )
        async with session_scope() as session:
            rows = await repo.list_pending_drafts(session, limit=10)
            ids = [r.id for r in rows]
            assert ids == sorted(ids)

    _run_with_db(url, body)


def test_reject_from_pending(tmp_path) -> None:
    reset_metrics()
    url = f"sqlite+aiosqlite:///{tmp_path / 'draft_reject.db'}"

    async def body() -> None:
        async with session_scope() as session:
            d = await repo.create_draft(
                session,
                content="r",
                content_hash=sha256_hex("r"),
                sources_payload=[{"channel": "@a", "message_id": 3}],
            )
            did = int(d.id)
            assert await repo.reject_draft(session, did) is True
            assert await repo.reject_draft(session, did) is True
        assert snapshot()["drafts_rejected"] == 1

        async with session_scope() as session:
            d2 = await repo.create_draft(
                session,
                content="r2",
                content_hash=sha256_hex("r2"),
                sources_payload=[{"channel": "@a", "message_id": 4}],
            )
            did2 = int(d2.id)
            assert await repo.approve_draft(session, did2) is True
            assert await repo.reject_draft(session, did2) is True

    _run_with_db(url, body)


def test_mark_failed_and_reset(tmp_path) -> None:
    reset_metrics()
    url = f"sqlite+aiosqlite:///{tmp_path / 'draft_failed.db'}"

    async def body() -> None:
        async with session_scope() as session:
            d = await repo.create_draft(
                session,
                content="f",
                content_hash=sha256_hex("f"),
                sources_payload=[{"channel": "@a", "message_id": 5}],
            )
            did = int(d.id)
            assert await repo.approve_draft(session, did) is True
            assert await repo.mark_draft_publishing(session, did) is True
            assert await repo.mark_draft_failed(session, did, reason="x") is True
            assert await repo.mark_draft_failed(session, did, reason="x") is True
        assert snapshot()["publish_failures"] >= 1

        async with session_scope() as session:
            assert await repo.reset_failed_draft_to_pending(session, did) is True
            row = await repo.get_draft_by_id(session, did)
            assert row is not None
            assert row.status == DraftStatus.PENDING.value

    _run_with_db(url, body)
