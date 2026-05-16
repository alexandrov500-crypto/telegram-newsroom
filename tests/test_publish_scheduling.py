from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from db import repository as repo
from db.session import close_db, init_db, session_scope
from tests.conftest import minimal_test_settings
from utils.schedule_parse import parse_draft_schedule_at
from utils.text_hash import sha256_hex


def test_parse_schedule_hhmm() -> None:
    s = minimal_test_settings(newsroom_timezone="UTC")
    now = datetime(2026, 5, 12, 10, 0, 0, tzinfo=timezone.utc)
    at = parse_draft_schedule_at("18:30", now=now, tz_name=s.newsroom_timezone)
    assert at is not None
    assert at.hour == 18 and at.minute == 30


def test_schedule_and_list_due(tmp_path) -> None:
    url = f"sqlite+aiosqlite:///{tmp_path / 'sched.db'}"

    async def body() -> None:
        await close_db()
        await init_db(url)
        try:
            from db.repository import utcnow

            when = utcnow() - timedelta(minutes=1)
            async with session_scope() as session:
                d = await repo.create_draft(
                    session,
                    content="s",
                    content_hash=sha256_hex("s"),
                    sources_payload=[{"channel": "@a", "message_id": 1}],
                )
                did = int(d.id)
                assert await repo.approve_draft(session, did) is True
                assert await repo.schedule_draft_publish(session, did, when=when) is True
            async with session_scope() as session:
                ids = await repo.list_due_scheduled_draft_ids(session, limit=5)
                assert did in ids
                listed = await repo.list_scheduled_drafts(session, limit=10)
                assert any(x.id == did for x in listed)
        finally:
            await close_db()

    asyncio.run(body())
