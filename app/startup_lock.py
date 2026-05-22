"""Process-level startup lock under runtime state dir (fail-fast on duplicate live instance)."""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_LOCK_HELD_PATH: Path | None = None


def _lock_path(runtime_dir: str) -> Path:
    return Path(runtime_dir).expanduser().resolve() / "start.lock"


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _read_lock(path: Path) -> dict[str, Any] | None:
    try:
        raw = path.read_text(encoding="utf-8").strip()
        if not raw:
            return None
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def acquire_runtime_startup_lock(settings: Any) -> None:
    """
    Atomic create of start.lock. If another live process holds it, raise RuntimeError.
    Stale locks (dead pid) are removed once and creation retried.
    """
    global _LOCK_HELD_PATH
    runtime_dir = str(getattr(settings, "runtime_state_dir", "var/runtime"))
    path = _lock_path(runtime_dir)
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "pid": os.getpid(),
        "started_at_unix": time.time(),
    }
    body = (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")

    for attempt in (1, 2):
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            existing = _read_lock(path)
            other_pid = int(existing.get("pid", 0)) if existing else 0
            if other_pid and other_pid != os.getpid() and _pid_alive(other_pid):
                raise RuntimeError(
                    f"Another newsroom process holds startup lock (pid={other_pid}, lock={path})"
                )
            try:
                path.unlink(missing_ok=True)
            except OSError as exc:
                raise RuntimeError(f"Cannot clear stale startup lock at {path}: {exc}") from exc
            logger.warning("startup lock stale — removed and retrying (path=%s)", path)
            continue

        try:
            os.write(fd, body)
        finally:
            os.close(fd)
        _LOCK_HELD_PATH = path
        logger.info("runtime startup lock acquired path=%s pid=%s", path, os.getpid())
        return

    raise RuntimeError(f"Failed to acquire startup lock at {path}")


def release_runtime_startup_lock(settings: Any | None = None) -> None:
    """Remove lock file on graceful shutdown (idempotent)."""
    global _LOCK_HELD_PATH
    path = _LOCK_HELD_PATH
    if path is None and settings is not None:
        path = _lock_path(str(getattr(settings, "runtime_state_dir", "var/runtime")))
    if path is None:
        return
    try:
        path.unlink(missing_ok=True)
        logger.info("runtime startup lock released path=%s", path)
    except FileNotFoundError:
        pass
    except OSError as exc:
        logger.warning("startup lock release failed path=%s error=%s", path, exc)
    finally:
        _LOCK_HELD_PATH = None


def reset_startup_lock_for_tests() -> None:
    global _LOCK_HELD_PATH
    _LOCK_HELD_PATH = None
