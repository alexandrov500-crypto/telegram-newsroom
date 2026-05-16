from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot import handlers
from db import repository as repo
from db.models import DraftStatus
from db.session import close_db, init_db, session_scope
from tests.conftest import minimal_test_settings
from tests.helpers.publish_mocks import PUBLISH_DRAFT_TO_CHANNEL
from utils.metrics import reset_metrics, snapshot
from utils.text_hash import sha256_hex


def test_e2e_approve_publish_published(tmp_path, monkeypatch) -> None:
    reset_metrics()
    url = f"sqlite+aiosqlite:///{tmp_path / 'e2e_pub.db'}"

    async def body() -> None:
        await close_db()
        await init_db(url)
        try:
            settings = minimal_test_settings(database_url=url, admin_user_id=1, dry_run=False)
            async with session_scope() as session:
                d = await repo.create_draft(
                    session,
                    content="e2e story\nline2",
                    content_hash=sha256_hex("e2e story\nline2"),
                    sources_payload=[{"channel": "@src", "message_id": 9}],
                )
                did = int(d.id)

            bot = MagicMock()
            monkeypatch.setattr(
                PUBLISH_DRAFT_TO_CHANNEL,
                AsyncMock(return_value=555),
            )

            res = await handlers._admin_publish_draft_flow(bot, settings, did)
            assert res.outcome is handlers._PublishFlowOutcome.OK

            async with session_scope() as session:
                row = await repo.get_draft_by_id(session, did)
                assert row is not None
                assert row.status == DraftStatus.PUBLISHED.value

            assert snapshot()["drafts_published"] >= 1
            assert snapshot()["publishes"] >= 1
        finally:
            await close_db()

    asyncio.run(body())


def test_e2e_reject_flow(tmp_path) -> None:
    url = f"sqlite+aiosqlite:///{tmp_path / 'e2e_rej.db'}"

    async def body() -> None:
        await close_db()
        await init_db(url)
        try:
            async with session_scope() as session:
                d = await repo.create_draft(
                    session,
                    content="x",
                    content_hash=sha256_hex("x"),
                    sources_payload=[{"channel": "@a", "message_id": 1}],
                )
                did = int(d.id)
                assert await repo.reject_draft(session, did) is True
            async with session_scope() as session:
                row = await repo.get_draft_by_id(session, did)
                assert row is not None
                assert row.status == DraftStatus.REJECTED.value
        finally:
            await close_db()

    asyncio.run(body())


def test_e2e_publish_failure_then_retry(tmp_path, monkeypatch) -> None:
    reset_metrics()
    url = f"sqlite+aiosqlite:///{tmp_path / 'e2e_fail.db'}"

    async def body() -> None:
        await close_db()
        await init_db(url)
        try:
            settings = minimal_test_settings(database_url=url, admin_user_id=1, dry_run=False)
            async with session_scope() as session:
                d = await repo.create_draft(
                    session,
                    content="fail then ok",
                    content_hash=sha256_hex("fail then ok"),
                    sources_payload=[{"channel": "@a", "message_id": 2}],
                )
                did = int(d.id)

            bot = MagicMock()
            pub = AsyncMock(side_effect=[RuntimeError("telegram down"), 777])
            monkeypatch.setattr(PUBLISH_DRAFT_TO_CHANNEL, pub)

            r1 = await handlers._admin_publish_draft_flow(bot, settings, did)
            assert r1.outcome is handlers._PublishFlowOutcome.SEND_FAILED

            async with session_scope() as session:
                row = await repo.get_draft_by_id(session, did)
                assert row is not None
                assert row.status == DraftStatus.FAILED.value

            r2 = await handlers._admin_publish_draft_flow(bot, settings, did)
            assert r2.outcome is handlers._PublishFlowOutcome.OK

            async with session_scope() as session:
                row = await repo.get_draft_by_id(session, did)
                assert row is not None
                assert row.status == DraftStatus.PUBLISHED.value
            assert pub.await_count == 2
        finally:
            await close_db()

    asyncio.run(body())


def test_e2e_duplicate_second_publish_no_extra_send(tmp_path, monkeypatch) -> None:
    url = f"sqlite+aiosqlite:///{tmp_path / 'e2e_dup.db'}"

    async def body() -> None:
        await close_db()
        await init_db(url)
        try:
            settings = minimal_test_settings(database_url=url, admin_user_id=1, dry_run=False)
            async with session_scope() as session:
                d = await repo.create_draft(
                    session,
                    content="dup",
                    content_hash=sha256_hex("dup"),
                    sources_payload=[{"channel": "@a", "message_id": 3}],
                )
                did = int(d.id)

            bot = MagicMock()
            pub = AsyncMock(return_value=900)
            monkeypatch.setattr(PUBLISH_DRAFT_TO_CHANNEL, pub)

            r1 = await handlers._admin_publish_draft_flow(bot, settings, did)
            assert r1.outcome is handlers._PublishFlowOutcome.OK
            r2 = await handlers._admin_publish_draft_flow(bot, settings, did)
            assert r2.outcome is handlers._PublishFlowOutcome.ALREADY_HANDLED
            assert pub.await_count == 1
        finally:
            await close_db()

    asyncio.run(body())
