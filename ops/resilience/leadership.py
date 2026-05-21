"""File-based leadership locks (runtime, publish, scheduler) with stale recovery."""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, IO

from ops.resilience.paths import locks_dir

logger = logging.getLogger(__name__)

try:
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None  # type: ignore[assignment]


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


@dataclass
class LeadershipLease:
    name: str
    path: Path
    _fp: IO[str] | None = None
    acquired: bool = False

    def _read_holder(self) -> dict[str, Any]:
        if self._fp is None:
            return {}
        try:
            self._fp.seek(0)
            raw = self._fp.read().strip()
            return json.loads(raw) if raw else {}
        except Exception:
            return {}

    def acquire(
        self,
        *,
        runtime_id: str,
        allow_stale_recovery: bool = True,
        lease_ttl_sec: float = 120.0,
    ) -> bool:
        if fcntl is None:
            logger.warning("leadership_lock_unavailable name=%s", self.name)
            self.acquired = True
            return True
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fp = open(self.path, "a+", encoding="utf-8")
        try:
            fcntl.flock(self._fp.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            holder = self._read_holder()
            stale_pid = int(holder.get("pid") or 0)
            holder_ts = float(holder.get("ts_unix") or 0)
            stale_time = time.time() - holder_ts > lease_ttl_sec
            if allow_stale_recovery and (not _pid_alive(stale_pid) or stale_time):
                logger.warning(
                    "leadership_stale_recovery name=%s stale_pid=%s",
                    self.name,
                    stale_pid,
                )
                try:
                    fcntl.flock(self._fp.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    self._fp.close()
                    self._fp = None
                    self.acquired = False
                    return False
            else:
                self._fp.close()
                self._fp = None
                self.acquired = False
                return False
        payload = {
            "name": self.name,
            "pid": os.getpid(),
            "runtime_id": runtime_id,
            "ts_unix": time.time(),
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        self._fp.seek(0)
        self._fp.truncate()
        self._fp.write(json.dumps(payload))
        self._fp.flush()
        self.acquired = True
        return True

    def release(self) -> None:
        if self._fp is None:
            return
        try:
            if fcntl is not None:
                fcntl.flock(self._fp.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        try:
            self._fp.close()
        except OSError:
            pass
        self._fp = None
        self.acquired = False


class LeadershipCoordinator:
    def __init__(self, runtime_dir: str) -> None:
        base = locks_dir(runtime_dir)
        self.runtime = LeadershipLease("runtime", base / "runtime.lock")
        self.publish = LeadershipLease("publish", base / "publish_leader.lock")
        self.scheduler = LeadershipLease("scheduler", base / "scheduler_leader.lock")

    def acquire_all(self, *, runtime_id: str) -> dict[str, bool]:
        return {
            "runtime": self.runtime.acquire(runtime_id=runtime_id),
            "publish": self.publish.acquire(runtime_id=runtime_id),
            "scheduler": self.scheduler.acquire(runtime_id=runtime_id),
        }

    def release_all(self) -> None:
        self.runtime.release()
        self.publish.release()
        self.scheduler.release()

    def snapshot(self) -> dict[str, Any]:
        return {
            "runtime_acquired": self.runtime.acquired,
            "publish_acquired": self.publish.acquired,
            "scheduler_acquired": self.scheduler.acquired,
        }


_coordinator: LeadershipCoordinator | None = None


def get_leadership(runtime_dir: str) -> LeadershipCoordinator:
    global _coordinator
    if _coordinator is None:
        _coordinator = LeadershipCoordinator(runtime_dir)
    return _coordinator


def require_publish_leadership(runtime_dir: str) -> bool:
    coord = get_leadership(runtime_dir)
    return coord.publish.acquired
