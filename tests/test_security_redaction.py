"""Security redaction utilities (opt-in)."""

from __future__ import annotations

import os

import pytest

from utils.security_redaction import redact_mapping, redact_text, redaction_enabled


@pytest.fixture
def redaction_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECURITY_REDACTION", "1")


def test_redaction_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SECURITY_REDACTION", raising=False)
    assert redaction_enabled() is False
    assert redact_text("sk-abcdefghijklmnop") == "sk-abcdefghijklmnop"


def test_redaction_masks_openai_key(redaction_on: None) -> None:
    assert redaction_enabled() is True
    out = redact_text("key sk-abcdefghijklmnopqrstuvwxyz here")
    assert "sk-***REDACTED***" in out
    assert "abcdefghijklmnopqrstuvwxyz" not in out


def test_redaction_mapping_sensitive_fields(redaction_on: None) -> None:
    m = redact_mapping({"bot_token": "123456:ABCDEF-secret", "ok": "visible"})
    assert m["bot_token"] == "***REDACTED***"
    assert m["ok"] == "visible"


def test_redaction_idempotent(redaction_on: None) -> None:
    once = redact_text("sk-abc12345678")
    twice = redact_text(once)
    assert once == twice
