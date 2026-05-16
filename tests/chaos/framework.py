"""Reusable chaos injectors for deterministic reliability tests."""

from __future__ import annotations

import asyncio
import sqlite3
import time
import zipfile
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator, Callable
from unittest.mock import AsyncMock, MagicMock

from worker.job_queue import JobEnvelope, JobKind, JobRetryMeta


@dataclass
class ChaosTimeline:
    """Ordered recovery evidence for assertions."""

    events: list[dict[str, Any]] = field(default_factory=list)

    def record(self, phase: str, **fields: Any) -> None:
        self.events.append({"ts": time.time(), "phase": phase, **fields})

    def phases(self) -> list[str]:
        return [str(e["phase"]) for e in self.events]


class RecordingRetryTransport:
    """Captures ack/enqueue ordering for worker retry chaos tests."""

    def __init__(self, *, fail_enqueue: bool = False) -> None:
        self.order: list[str] = []
        self.fail_enqueue = fail_enqueue
        self.enqueued: list[JobEnvelope] = []

    async def ack(self, kind: JobKind, raw: str, *, delivery_id: str = "") -> None:
        self.order.append("ack")

    async def enqueue(self, env: JobEnvelope) -> None:
        if self.fail_enqueue:
            raise RuntimeError("chaos: enqueue_failed")
        self.order.append("enqueue")
        self.enqueued.append(env)

    async def nack_dlq(self, *args: Any, **kwargs: Any) -> None:
        self.order.append("dlq")


@contextmanager
def inject_sqlite_busy(db_path: Path, *, hold_sec: float = 0.05):
    """Hold a RESERVED lock briefly to simulate SQLITE_BUSY."""
    conn = sqlite3.connect(db_path)
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield
        time.sleep(hold_sec)
    finally:
        conn.rollback()
        conn.close()


@contextmanager
def inject_delayed_sleep(monkeypatch: Any, delay_sec: float):
    """Slow down asyncio.sleep for retry backoff tests."""
    real_sleep = asyncio.sleep

    async def slow_sleep(sec: float) -> None:
        await real_sleep(min(sec, delay_sec))

    monkeypatch.setattr(asyncio, "sleep", slow_sleep)
    yield


def corrupt_zip_entry(zip_path: Path, member: str) -> None:
    """Flip bytes in a zip member (deterministic corruption)."""
    data = bytearray(zip_path.read_bytes())
    if len(data) > 64:
        data[32] ^= 0xFF
    zip_path.write_bytes(bytes(data))


def write_partial_snapshot(target: Path, *, files: dict[str, str]) -> None:
    rt = target / "runtime"
    rt.mkdir(parents=True, exist_ok=True)
    for name, body in files.items():
        (rt / name).write_text(body, encoding="utf-8")


def make_fake_redis(
    *,
    set_ok: bool = True,
    set_raises: Exception | None = None,
    slow_set_sec: float = 0.0,
) -> MagicMock:
    r = MagicMock()

    async def _set(*args: Any, **kwargs: Any) -> bool:
        if slow_set_sec:
            await asyncio.sleep(slow_set_sec)
        if set_raises:
            raise set_raises
        return set_ok

    r.set = AsyncMock(side_effect=_set)
    r.delete = AsyncMock(return_value=1)
    return r


@asynccontextmanager
async def inject_redis_client(monkeypatch: Any, fake: MagicMock) -> AsyncIterator[MagicMock]:
    async def _get() -> MagicMock:
        return fake

    monkeypatch.setattr("utils.redis_client.get_redis", _get)
    yield fake


def simulate_network_timeout() -> TimeoutError:
    return TimeoutError("chaos: simulated network timeout")


def simulate_partial_publish_failure(*, succeeded_chunks: int) -> Callable[[int], bool]:
    """Return predicate: True if chunk index should succeed."""

    def ok(chunk_idx: int) -> bool:
        return chunk_idx < succeeded_chunks

    return ok


@dataclass
class ProcessKillScenario:
    """Labels for worker crash injection tests (no real SIGKILL in CI)."""

    name: str
    crash_before_ack: bool = False
    crash_after_ack: bool = False
    interrupt_during_backoff: bool = False


CRASH_SCENARIOS: tuple[ProcessKillScenario, ...] = (
    ProcessKillScenario("before_ack", crash_before_ack=True),
    ProcessKillScenario("after_ack", crash_after_ack=True),
    ProcessKillScenario("during_backoff", interrupt_during_backoff=True),
)
