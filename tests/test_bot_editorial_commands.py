from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.enums import ChatType
from aiogram.types import Chat, User

from bot import admin_handlers as handlers
from db import repository as repo
from db.session import close_db, init_db, session_scope
from tests.conftest import minimal_test_settings
from utils.text_hash import sha256_hex


def _msg(*, uid: int, text: str, chat_id: int = 1):
    u = User(id=uid, is_bot=False, first_name="A")
    chat = Chat(id=chat_id, type=ChatType.PRIVATE)
    m = MagicMock()
    m.message_id = 1
    m.date = 0
    m.chat = chat
    m.from_user = u
    m.text = text
    m.answer = AsyncMock()
    return m


@pytest.fixture
def sqlite_url(tmp_path) -> str:
    return f"sqlite+aiosqlite:///{tmp_path / 'bot_editorial.db'}"


@pytest.fixture(autouse=True)
def db_init(sqlite_url: str):
    asyncio.run(close_db())
    asyncio.run(init_db(sqlite_url))
    yield
    asyncio.run(close_db())


def test_cmd_queue_lists_pending(sqlite_url: str) -> None:
    settings = minimal_test_settings(database_url=sqlite_url, admin_user_id=1)

    async def prep() -> None:
        async with session_scope() as session:
            await repo.create_draft(
                session,
                content="hello queue",
                content_hash=sha256_hex("hello queue"),
                sources_payload=[{"channel": "@c", "message_id": 1}],
            )

    asyncio.run(prep())

    async def run() -> None:
        msg = _msg(uid=1, text="/queue")
        await handlers.cmd_queue(msg, settings)
        assert msg.answer.await_count == 1
        arg = msg.answer.await_args[0][0]
        assert "hello queue" in arg or "#1" in arg
        assert "page 1" in arg

    asyncio.run(run())


def test_cmd_draft_preview(sqlite_url: str) -> None:
    settings = minimal_test_settings(database_url=sqlite_url, admin_user_id=1)

    async def run() -> None:
        async with session_scope() as session:
            d = await repo.create_draft(
                session,
                content="Title line\nbody",
                content_hash=sha256_hex("x"),
                sources_payload=[{"channel": "@c", "message_id": 2}],
            )
            did = int(d.id)
        msg = _msg(uid=1, text=f"/draft {did}")
        await handlers.cmd_draft(msg, settings)
        text = msg.answer.await_args[0][0]
        assert "Title line" in text
        assert f"<code>{did}</code>" in text or f"Draft ID: {did}" in text

    asyncio.run(run())


def test_cmd_approve_dry_run_no_network(sqlite_url: str) -> None:
    settings = minimal_test_settings(database_url=sqlite_url, admin_user_id=1, dry_run=True)
    bot = MagicMock()

    async def run() -> None:
        async with session_scope() as session:
            d = await repo.create_draft(
                session,
                content="pub",
                content_hash=sha256_hex("pub"),
                sources_payload=[{"channel": "@c", "message_id": 3}],
            )
            did = int(d.id)
        msg = _msg(uid=1, text=f"/approve {did}")
        await handlers.cmd_approve(msg, bot, settings)
        bot.send_message.assert_not_called()
        async with session_scope() as session:
            row = await repo.get_draft_by_id(session, did)
            assert row is not None
            assert row.status == "pending"

    asyncio.run(run())


def test_cmd_reject(sqlite_url: str) -> None:
    settings = minimal_test_settings(database_url=sqlite_url, admin_user_id=1)

    async def run() -> None:
        async with session_scope() as session:
            d = await repo.create_draft(
                session,
                content="rej",
                content_hash=sha256_hex("rej"),
                sources_payload=[{"channel": "@c", "message_id": 4}],
            )
            did = int(d.id)
        msg = _msg(uid=1, text=f"/reject {did}")
        await handlers.cmd_reject(msg, settings)
        async with session_scope() as session:
            row = await repo.get_draft_by_id(session, did)
            assert row is not None
            assert row.status == "rejected"

    asyncio.run(run())
