from __future__ import annotations

from bot import handlers
from tests.conftest import minimal_test_settings
from utils.runtime_dump import sanitize_settings_for_dump
from utils.telegram_html import sanitize_telegram_html_output


def test_sanitize_html_strips_scriptish_content() -> None:
    out = sanitize_telegram_html_output('<div onclick="evil(1)">x</div>')
    assert "onclick" not in out.lower()


def test_callback_draft_id_rejects_huge() -> None:
    assert handlers._parse_callback_draft_id("pub:999999999999") is None


def test_slash_command_id_rejects_huge() -> None:
    assert handlers._parse_slash_command_int("draft", "/draft 999999999999") is None


def test_sanitize_settings_masks_secrets() -> None:
    s = minimal_test_settings()
    d = sanitize_settings_for_dump(s)
    assert d["openai_api_key"] == "<redacted>"
    assert "***" in str(d.get("bot_token", "")) or d.get("bot_token") == "<redacted>"
    assert "database_url" in d
