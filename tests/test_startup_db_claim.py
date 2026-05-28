from __future__ import annotations

import asyncio
import os
from unittest.mock import patch

import pytest

from app.runtime_notifications import maybe_send_process_startup_notification, reset_notification_state_for_tests
from db.runtime_ops_repository import try_claim_startup_notification_in_db
from db.session import init_db, session_scope
from tests.conftest import minimal_test_settings


@pytest.fixture
async def _db(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path / 'claim.db'}"
    await init_db(url)
    yield url


def test_db_claim_blocks_second_within_window(tmp_path) -> None:
    async def body() -> None:
        await init_db(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
        async with session_scope() as session:
            assert await try_claim_startup_notification_in_db(
                session,
                window_sec=3600.0,
                process_uuid="aaa",
            )
        async with session_scope() as session:
            assert not await try_claim_startup_notification_in_db(
                session,
                window_sec=3600.0,
                process_uuid="bbb",
            )

    asyncio.run(body())


def test_startup_notify_respects_db_claim(tmp_path) -> None:
    from unittest.mock import AsyncMock, MagicMock

    from app.ops.runtime.active_runtime import register_active_runtime
    import os

    async def body() -> None:
        from db.session import close_db

        await close_db()
        env = {
            "NEWSROOM_LOCK_BY_BOT_TOKEN": "false",
            "RUNTIME_SINGLETON_DISABLED": "true",
        }
        with patch.dict(os.environ, env):
            await init_db(f"sqlite+aiosqlite:///{tmp_path / 'notify.db'}")
            reset_notification_state_for_tests()
            bot = MagicMock()
            bot.send_message = AsyncMock()
            rd = str(tmp_path / "runtime")
            db_url = f"sqlite+aiosqlite:///{tmp_path / 'notify.db'}"
            settings = minimal_test_settings(
                send_startup_notification=True,
                notification_rate_limit_minutes=60,
                runtime_state_dir=rd,
                database_url=db_url,
            )
            register_active_runtime(rd, runtime_id="t1", pid=os.getpid())

            assert await maybe_send_process_startup_notification(bot, settings) is True
            reset_notification_state_for_tests()
            register_active_runtime(rd, runtime_id="t2", pid=os.getpid())
            assert await maybe_send_process_startup_notification(bot, settings) is False
            assert bot.send_message.await_count == 1

    asyncio.run(body())
