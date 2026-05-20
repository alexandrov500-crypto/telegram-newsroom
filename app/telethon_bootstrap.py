"""Telethon session bootstrap detection and operator recovery hints."""
from __future__ import annotations

from pathlib import Path

from app.config import Settings

TELETHON_RECOVERY_CLI = (
    "python gen_session.py --write-env   # interactive login, writes TELETHON_SESSION_STRING\n"
    "python gen_session.py --verify      # verify existing session in .env\n"
    "python tools/import_session_to_env.py  # import exported string into .env"
)


def telethon_session_configured(settings: Settings) -> bool:
    if (settings.telethon_session_string or "").strip():
        return True
    path = (settings.telethon_session_path or "").strip()
    return bool(path and Path(path).is_file())


def telethon_missing_detail(settings: Settings) -> str:
    if settings.telethon_session_path:
        return f"TELETHON_SESSION_PATH file missing: {settings.telethon_session_path}"
    return "TELETHON_SESSION_STRING empty and TELETHON_SESSION_PATH unset"
