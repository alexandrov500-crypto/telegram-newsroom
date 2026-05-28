from __future__ import annotations

import os
from unittest.mock import patch

from app.config import _parse_admin_user_ids, _parse_optional_chat_id, load_settings


def test_parse_admin_user_ids_merges_env() -> None:
    with patch.dict(os.environ, {"ADMIN_USER_IDS": "111,222"}, clear=False):
        ids = _parse_admin_user_ids(167395657)
    assert ids == frozenset({167395657, 111, 222})


def test_parse_optional_chat_id_empty() -> None:
    with patch.dict(os.environ, {"MODERATION_CHAT_ID": ""}, clear=False):
        assert _parse_optional_chat_id("MODERATION_CHAT_ID") is None


def test_load_settings_has_admin_user_ids() -> None:
    with patch.dict(
        os.environ,
        {
            "OPENAI_API_KEY": "sk-test",
            "BOT_TOKEN": "123:ABC",
            "TELEGRAM_API_ID": "1",
            "TELEGRAM_API_HASH": "h",
            "TELETHON_SESSION_STRING": "s",
            "ADMIN_USER_ID": "42",
            "TARGET_CHANNEL_ID": "-1001",
            "SOURCE_CHANNELS": "@x",
        },
        clear=False,
    ):
        s = load_settings()
    assert 42 in s.admin_user_ids
