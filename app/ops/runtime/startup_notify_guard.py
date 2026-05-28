"""Cross-process lock so only one live newsroom sends the Telegram startup banner."""

from __future__ import annotations

import fcntl
import json
import logging
import os
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_LOCK_NAME = "startup_notify.lock"
_fd: int | None = None


def _lock_path(runtime_dir: str) -> Path:
    return Path(runtime_dir).expanduser().resolve() / _LOCK_NAME


def try_acquire_startup_notification_lock(runtime_dir: str) -> bool:
    """
    Non-blocking flock — held until process exit (or release_startup_notification_lock).
    Prevents duplicate «Newsroom started» when two processes overlap during docker restart.
    """
    global _fd
    if _fd is not None:
        return False

    path = _lock_path(runtime_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        logger.info("startup notify lock busy path=%s — another process owns notify", path)
        return False

    payload = {
        "pid": os.getpid(),
        "claimed_at_unix": time.time(),
    }
    os.ftruncate(fd, 0)
    os.lseek(fd, 0, os.SEEK_SET)
    os.write(fd, (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8"))
    _fd = fd
    return True


def release_startup_notification_lock() -> None:
    global _fd
    if _fd is None:
        return
    try:
        fcntl.flock(_fd, fcntl.LOCK_UN)
    except OSError:
        pass
    try:
        os.close(_fd)
    except OSError:
        pass
    _fd = None


def reset_startup_notification_lock_for_tests() -> None:
    release_startup_notification_lock()
