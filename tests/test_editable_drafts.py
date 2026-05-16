from __future__ import annotations

import asyncio

from db import repository as repo
from db.session import close_db, init_db, session_scope
from utils.metrics import reset_metrics, snapshot
from utils.text_hash import sha256_hex


def test_update_title_and_summary(tmp_path) -> None:
    reset_metrics()
    url = f"sqlite+aiosqlite:///{tmp_path / 'edit.db'}"

    async def body() -> None:
        await close_db()
        await init_db(url)
        try:
            async with session_scope() as session:
                d = await repo.create_draft(
                    session,
                    content="orig",
                    content_hash=sha256_hex("orig"),
                    sources_payload=[{"channel": "@a", "message_id": 1}],
                )
                did = int(d.id)
            async with session_scope() as session:
                assert await repo.update_draft_title(session, did, title="New Title") is True
                assert await repo.update_draft_summary(session, did, summary="New summary body") is True
            async with session_scope() as session:
                row = await repo.get_draft_by_id(session, did)
                assert row is not None
                assert row.editor_title == "New Title"
                assert "New summary" in (row.editor_summary or "")
                hist = row.edit_history or "[]"
                assert "edit_title" in hist
            assert snapshot().get("draft_edits", 0) >= 2
        finally:
            await close_db()

    asyncio.run(body())


def test_empty_edit_rejected(tmp_path) -> None:
    url = f"sqlite+aiosqlite:///{tmp_path / 'edit2.db'}"

    async def body() -> None:
        await close_db()
        await init_db(url)
        try:
            async with session_scope() as session:
                d = await repo.create_draft(
                    session,
                    content="x",
                    content_hash=sha256_hex("x"),
                    sources_payload=[{"channel": "@a", "message_id": 2}],
                )
                did = int(d.id)
                assert await repo.update_draft_title(session, did, title="   ") is False
                assert await repo.update_draft_summary(session, did, summary="") is False
        finally:
            await close_db()

    asyncio.run(body())
