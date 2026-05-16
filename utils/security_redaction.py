"""Opt-in deterministic secret redaction (SECURITY_REDACTION=1)."""

from __future__ import annotations

import os
import re
from typing import Any

# Stable masks — do not embed recovered secret length hints beyond coarse class.
_MASK = "***REDACTED***"

_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bsk-[A-Za-z0-9]{8,}\b"), f"sk-{_MASK}"),
    (re.compile(r"\b\d{6,}:[A-Za-z0-9_-]{20,}\b"), f"<bot_token:{_MASK}>"),  # Telegram bot token
    (
        re.compile(
            r"(?i)(api[_-]?key|token|secret|password|authorization)\s*[:=]\s*['\"]?([^'\"\s]{8,})"
        ),
        r"\1=***REDACTED***",
    ),
    (re.compile(r"redis://:[^@\s]+@"), "redis://:***REDACTED***@"),
    (re.compile(r"redis://[^:\s]+:[^@\s]+@"), "redis://user:***REDACTED***@"),
    (re.compile(r"(?i)Bearer\s+[A-Za-z0-9._-]{12,}"), f"Bearer {_MASK}"),
    (re.compile(r"(?i)TELETHON_SESSION_STRING=\S+"), f"TELETHON_SESSION_STRING={_MASK}"),
    (re.compile(r"(?i)OPENAI_API_KEY=\S+"), f"OPENAI_API_KEY={_MASK}"),
    (re.compile(r"(?i)BOT_TOKEN=\S+"), f"BOT_TOKEN={_MASK}"),
)

_SENSITIVE_FIELD_NAMES = frozenset(
    {
        "bot_token",
        "openai_api_key",
        "telethon_session_string",
        "password",
        "secret",
        "authorization",
        "api_key",
        "token",
        "redis_url",
    }
)


def redaction_enabled() -> bool:
    return os.getenv("SECURITY_REDACTION", "").strip().lower() in {"1", "true", "yes", "on"}


def redact_text(text: str) -> str:
    """Deterministic string redaction (idempotent on already-redacted text)."""
    if not text or not redaction_enabled():
        return text
    out = text
    for pattern, repl in _PATTERNS:
        out = pattern.sub(repl, out)
    return out


def redact_mapping(fields: dict[str, Any]) -> dict[str, Any]:
    if not redaction_enabled():
        return fields
    safe: dict[str, Any] = {}
    for k, v in fields.items():
        key_lower = str(k).lower()
        if key_lower in _SENSITIVE_FIELD_NAMES:
            safe[k] = _MASK
            continue
        if isinstance(v, str):
            safe[k] = redact_text(v)
        elif isinstance(v, dict):
            safe[k] = redact_mapping(v)
        elif isinstance(v, list):
            safe[k] = [redact_text(x) if isinstance(x, str) else x for x in v[:64]]
        else:
            safe[k] = v
    return safe


def sanitize_dict_for_export(data: dict[str, Any]) -> dict[str, Any]:
    """Evidence/diagnostic export hook; always redacts when flag on."""
    return redact_mapping(data) if redaction_enabled() else dict(data)


def redact_traceback(tb: str) -> str:
    return redact_text(tb)


def redact_env_snapshot(env: dict[str, str]) -> dict[str, str]:
    if not redaction_enabled():
        return dict(env)
    out: dict[str, str] = {}
    for k, v in env.items():
        ku = k.upper()
        if any(x in ku for x in ("TOKEN", "KEY", "SECRET", "PASSWORD", "SESSION")):
            out[k] = _MASK
        else:
            out[k] = redact_text(v)
    return out
