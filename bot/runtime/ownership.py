from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any

from bot.config import project_root
from bot.runtime.instance import RuntimeIdentity

logger = logging.getLogger(__name__)

try:
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None  # type: ignore[assignment]


class RuntimeOwnershipError(RuntimeError):
    """Another operator process holds the runtime lock."""

    def __init__(self, message: str, *, holder: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.holder = holder or {}


@dataclass
class RuntimeOwnershipLock:
    path: Path
    _fp: IO[str] | None = None

    @classmethod
    def default_path(cls) -> Path:
        raw = os.getenv("RUNTIME_LOCK_FILE", "").strip()
        if raw:
            return Path(raw).expanduser()
        return project_root() / "var" / "run" / "operator-runtime.lock"

    @staticmethod
    def _pid_alive(pid: int) -> bool:
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True

    def _read_holder(self) -> dict[str, Any]:
        if self._fp is None:
            return {}
        try:
            self._fp.seek(0)
            raw = self._fp.read().strip()
            if not raw:
                return {}
            return json.loads(raw)
        except Exception:
            return {}

    def acquire(self, identity: RuntimeIdentity, *, allow_stale_recovery: bool = True) -> None:
        if fcntl is None:
            logger.warning("event=runtime_ownership_lock_unavailable platform=non_unix")
            return

        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fp = open(self.path, "a+", encoding="utf-8")
        try:
            fcntl.flock(self._fp.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            holder = self._read_holder()
            stale_pid = int(holder.get("pid", 0) or 0)
            if allow_stale_recovery and stale_pid and not self._pid_alive(stale_pid):
                logger.warning(
                    "event=runtime_ownership_stale_lock_recovered stale_pid=%s",
                    stale_pid,
                )
                try:
                    fcntl.flock(self._fp.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    holder = self._read_holder() or holder
                    self._fp.close()
                    self._fp = None
                    raise RuntimeOwnershipError(
                        "Another operator runtime already active. Startup aborted.",
                        holder=holder,
                    ) from None
            else:
                holder = self._read_holder() or holder
                self._fp.close()
                self._fp = None
                raise RuntimeOwnershipError(
                    "Another operator runtime already active. Startup aborted.",
                    holder=holder,
                ) from None

        payload = identity.to_dict()
        self._fp.seek(0)
        self._fp.truncate()
        json.dump(payload, self._fp)
        self._fp.write("\n")
        self._fp.flush()
        logger.info(
            "event=runtime_ownership_acquired lock=%s instance=%s pid=%s",
            self.path,
            identity.runtime_instance_id,
            identity.pid,
        )

    def release(self) -> None:
        if self._fp is None or fcntl is None:
            return
        try:
            fcntl.flock(self._fp.fileno(), fcntl.LOCK_UN)
            self._fp.close()
        except Exception:
            logger.exception("event=runtime_ownership_release_failed")
        finally:
            self._fp = None


_ownership_lock: RuntimeOwnershipLock | None = None


def acquire_runtime_ownership(
    identity: RuntimeIdentity,
    *,
    enabled: bool | None = None,
) -> RuntimeOwnershipLock:
    global _ownership_lock
    if enabled is None:
        enabled = os.getenv("RUNTIME_OWNERSHIP_ENABLED", "true").lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
    if os.getenv("RUNTIME_ALLOW_MULTIPLE", "").lower() in ("1", "true", "yes"):
        enabled = False

    lock = RuntimeOwnershipLock(RuntimeOwnershipLock.default_path())
    if enabled:
        lock.acquire(identity)
    _ownership_lock = lock
    return lock


def release_runtime_ownership() -> None:
    global _ownership_lock
    if _ownership_lock is not None:
        _ownership_lock.release()
        _ownership_lock = None


def read_lock_holder(path: Path | None = None) -> dict[str, Any]:
    lock_path = path or RuntimeOwnershipLock.default_path()
    if not lock_path.is_file():
        return {}
    try:
        return json.loads(lock_path.read_text(encoding="utf-8").strip())
    except Exception:
        return {}


def abort_if_duplicate_runtime() -> None:
    """Fail fast before asyncio when another live holder owns the lock file."""
    holder = read_lock_holder()
    pid = int(holder.get("pid", 0) or 0)
    if pid and pid != os.getpid() and RuntimeOwnershipLock._pid_alive(pid):
        msg = (
            "Another operator runtime already active. Startup aborted.\n"
            f"  holder_pid={pid}\n"
            f"  instance={holder.get('runtime_instance_id', '?')}\n"
            f"  profile={holder.get('runtime_profile', '?')}\n"
            f"  started_at={holder.get('started_at', '?')}\n"
            "Run: python3 scripts/runtime_process_check.py\n"
            "Then: bash scripts/kill_all_operator_processes.sh"
        )
        print(msg, file=sys.stderr)
        raise SystemExit(1)
