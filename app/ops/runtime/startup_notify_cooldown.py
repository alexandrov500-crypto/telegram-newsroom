"""File-based startup notify cooldown (same host, shared lock dir per bot token)."""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_FILENAME = "last_startup_notify.json"


def try_claim_startup_notify_cooldown(lock_dir: str, *, window_sec: float) -> bool:
    """
    Returns True if this process may send the startup banner.
    Complements DB claim when local/VPS use different databases.
    """
    if window_sec <= 0:
        return True
    path = Path(lock_dir).expanduser().resolve() / _FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    now = time.time()
    try:
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                last = float(data.get("sent_at_unix") or 0)
                if (now - last) < window_sec:
                    logger.info(
                        "startup notify cooldown active path=%s age_sec=%.0f window_sec=%.0f",
                        path,
                        now - last,
                        window_sec,
                    )
                    return False
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        pass

    payload = {
        "sent_at_unix": now,
        "pid": os.getpid(),
    }
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    os.replace(tmp, path)
    return True
