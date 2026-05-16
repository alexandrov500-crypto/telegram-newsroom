from __future__ import annotations

import asyncio
import logging
from unittest.mock import MagicMock

import pytest
from telethon.errors import SessionPasswordNeededError

from collector.retry import with_telethon_retries


@pytest.fixture
def no_sleep(monkeypatch):
    async def _instant(_delay: float = 0.0) -> None:
        return None

    monkeypatch.setattr(asyncio, "sleep", _instant)


def test_retries_transient_oserror_then_success(no_sleep, caplog):
    caplog.set_level(logging.WARNING)
    calls = {"n": 0}

    async def op():
        calls["n"] += 1
        if calls["n"] < 3:
            raise OSError("transient")
        return "ok"

    async def body():
        return await with_telethon_retries("test_op", op, max_attempts=5, base_delay_s=0.01)

    out = asyncio.run(body())
    assert out == "ok"
    assert calls["n"] == 3
    assert any("transient error" in r.message.lower() for r in caplog.records)


def test_retry_limit_propagates_last_error(no_sleep):
    async def op():
        raise OSError("always fails")

    async def body():
        await with_telethon_retries("fail_op", op, max_attempts=3, base_delay_s=0.01)

    with pytest.raises(OSError, match="always fails"):
        asyncio.run(body())


def test_session_password_needed_not_retried(no_sleep):
    async def op():
        raise SessionPasswordNeededError(request=MagicMock())

    async def body():
        await with_telethon_retries("pwd", op, max_attempts=4, base_delay_s=0.01)

    with pytest.raises(SessionPasswordNeededError):
        asyncio.run(body())


def test_success_first_call_no_recovery_log(no_sleep, caplog):
    caplog.set_level(logging.INFO)

    async def op():
        return "first"

    async def body():
        return await with_telethon_retries("ok", op, max_attempts=3, base_delay_s=0.01)

    out = asyncio.run(body())
    assert out == "first"
    assert not any("recovered_after_retry" in r.message for r in caplog.records)
