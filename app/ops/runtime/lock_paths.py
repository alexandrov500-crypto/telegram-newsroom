"""Where flock locks live — per deployment dir or per bot token (same host)."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any


def _bot_token_from_settings(settings: Any) -> str:
    token = getattr(settings, "bot_token", None) or os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or ""
    return str(token).strip()


def lock_by_bot_token_enabled() -> bool:
    return os.getenv("NEWSROOM_LOCK_BY_BOT_TOKEN", "true").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def resolve_process_lock_dir(settings: Any) -> str:
    """
    Directory for ``newsroom.lock`` and ``startup_notify.lock``.

    Default: ``~/.newsroom/locks/<sha256(bot_token)[:16]>`` so two local processes
  with the same bot cannot both poll. State (DB path, ledger) stays in ``RUNTIME_STATE_DIR``.
    """
    runtime_dir = str(getattr(settings, "runtime_state_dir", None) or os.getenv("RUNTIME_STATE_DIR", "var/runtime"))
    if not lock_by_bot_token_enabled():
        return str(Path(runtime_dir).expanduser().resolve())

    token = _bot_token_from_settings(settings)
    if not token:
        return str(Path(runtime_dir).expanduser().resolve())

    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]
    base = Path(
        os.getenv(
            "NEWSROOM_GLOBAL_LOCK_DIR",
            str(Path.home() / ".newsroom" / "locks"),
        )
    ).expanduser()
    return str((base / digest).resolve())
