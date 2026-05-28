from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from aiogram import Dispatcher
from aiogram.enums import ChatType
from aiogram.types import Chat, User

from bot.admin_handlers import on_preview, on_reject, register_handlers
from db import repository as repo
from db.session import close_db, init_db, session_scope
from tests.conftest import minimal_test_settings
from utils.text_hash import sha256_hex


def _callback(*, uid: int, data: str, chat_id: int = 1):
    cb = MagicMock()
    cb.data = data
    cb.from_user = User(id=uid, is_bot=False, first_name="Op")
    cb.message = MagicMock()
    cb.message.chat = Chat(id=chat_id, type=ChatType.PRIVATE)
    cb.message.photo = None
    cb.message.video = None
    cb.message.edit_text = AsyncMock()
    cb.message.edit_caption = AsyncMock()
    cb.message.answer = AsyncMock()
    cb.answer = AsyncMock()
    return cb


def test_preview_callback_answers_and_replies(tmp_path) -> None:
    url = f"sqlite+aiosqlite:///{tmp_path / 'cb.db'}"

    async def body() -> None:
        await close_db()
        await init_db(url)
        settings = minimal_test_settings(database_url=url, admin_user_id=1, admin_user_ids=frozenset({1}))
        async with session_scope() as session:
            d = await repo.create_draft(
                session,
                content="Story body for preview",
                content_hash=sha256_hex("pv"),
                sources_payload=[{"channel": "@c", "message_id": 1}],
            )
            did = int(d.id)
        cb = _callback(uid=1, data=f"pre:{did}")
        await on_preview(cb, settings)
        assert cb.answer.await_count >= 1 or cb.message.answer.await_count >= 1
        await close_db()

    asyncio.run(body())


def test_reject_callback_updates_draft(tmp_path) -> None:
    url = f"sqlite+aiosqlite:///{tmp_path / 'rej.db'}"

    async def body() -> None:
        await close_db()
        await init_db(url)
        settings = minimal_test_settings(database_url=url, admin_user_id=1, admin_user_ids=frozenset({1}))
        async with session_scope() as session:
            d = await repo.create_draft(
                session,
                content="to reject",
                content_hash=sha256_hex("rj"),
                sources_payload=[{"channel": "@c", "message_id": 2}],
            )
            did = int(d.id)
        cb = _callback(uid=1, data=f"rej:{did}")
        await on_reject(cb, settings)
        async with session_scope() as session:
            row = await repo.get_draft_by_id(session, did)
            assert row is not None
            assert row.status == "rejected"
        await close_db()

    asyncio.run(body())


def test_dispatcher_registers_callback_query_handler() -> None:
    dp = Dispatcher()
    settings = minimal_test_settings()
    register_handlers(dp, settings)
    types = dp.resolve_used_update_types()
    assert "callback_query" in types
