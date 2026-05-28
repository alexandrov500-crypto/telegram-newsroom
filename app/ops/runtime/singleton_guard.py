"""Filesystem singleton lock — exactly one active newsroom runtime."""

from __future__ import annotations

import fcntl
import json
import logging
import os
import socket
import sys
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_LOCK_FILENAME = "newsroom.lock"
_guard: RuntimeSingletonGuard | None = None


def _singleton_disabled() -> bool:
    return os.getenv("RUNTIME_SINGLETON_DISABLED", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def lock_path_for_runtime(runtime_dir: str) -> Path:
    return Path(runtime_dir).expanduser().resolve() / _LOCK_FILENAME


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


class RuntimeSingletonGuard:
    """
    Advisory flock on ``newsroom.lock``.

    - ``acquire()``: non-blocking exclusive lock; returns True if this process is owner.
    - ``release()``: drops lock on graceful shutdown.
    """

    def __init__(self, runtime_dir: str) -> None:
        self._path = lock_path_for_runtime(runtime_dir)
        self._fd: int | None = None
        self._owner = False

    @property
    def path(self) -> Path:
        return self._path

    def is_owner(self) -> bool:
        return self._owner

    def acquire(self) -> bool:
        if self._owner:
            return True
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self._path, os.O_CREAT | os.O_RDWR, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(fd)
            holder = self._read_holder_metadata()
            logger.warning(
                "singleton lock held by another process path=%s holder=%s",
                self._path,
                holder,
            )
            return False

        payload = {
            "pid": os.getpid(),
            "started_at_unix": time.time(),
            "hostname": socket.gethostname(),
        }
        os.ftruncate(fd, 0)
        os.lseek(fd, 0, os.SEEK_SET)
        os.write(fd, (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8"))
        self._fd = fd
        self._owner = True
        global _guard
        _guard = self
        logger.info("singleton lock acquired path=%s pid=%s", self._path, os.getpid())
        return True

    def release(self) -> None:
        global _guard
        if self._fd is None:
            self._owner = False
            if _guard is self:
                _guard = None
            return
        try:
            fcntl.flock(self._fd, fcntl.LOCK_UN)
        except OSError as exc:
            logger.warning("singleton lock unlock failed: %s", exc)
        try:
            os.close(self._fd)
        except OSError:
            pass
        self._fd = None
        self._owner = False
        if _guard is self:
            _guard = None
        logger.info("singleton lock released path=%s", self._path)

    def _read_holder_metadata(self) -> dict[str, Any]:
        try:
            raw = self._path.read_text(encoding="utf-8").strip()
            if raw:
                data = json.loads(raw)
                if isinstance(data, dict):
                    pid = int(data.get("pid", 0))
                    if pid and _pid_alive(pid):
                        return data
        except (OSError, json.JSONDecodeError, ValueError):
            pass
        return {"pid": "unknown", "note": "lock_held"}


def get_singleton_guard(runtime_dir: str | None = None) -> RuntimeSingletonGuard:
    global _guard
    if _guard is None:
        rd = runtime_dir or os.getenv("RUNTIME_STATE_DIR", "var/runtime")
        _guard = RuntimeSingletonGuard(rd)
    return _guard


def reset_singleton_guard_for_tests() -> None:
    global _guard
    if _guard is not None:
        _guard.release()
    _guard = None


def enforce_singleton_or_exit(settings: Any) -> RuntimeSingletonGuard:
    """
    Acquire global singleton. If another live process holds the lock, exit 0 cleanly.
    """
    from app.ops.runtime.lock_paths import resolve_process_lock_dir

    lock_dir = resolve_process_lock_dir(settings)
    if _singleton_disabled():
        guard = get_singleton_guard(lock_dir)
        guard._owner = True  # noqa: SLF001 — test/dev bypass
        logger.warning("RUNTIME_SINGLETON_DISABLED=true — singleton bypassed")
        return guard

    global _guard
    _guard = RuntimeSingletonGuard(lock_dir)
    if not _guard.acquire():
        logger.info(
            "Not singleton owner — exiting without side effects (lock=%s)",
            _guard.path,
        )
        sys.exit(0)
    return _guard


def release_singleton_guard() -> None:
    global _guard
    if _guard is not None:
        _guard.release()
    _guard = None
