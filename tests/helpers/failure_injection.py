"""Controlled failure / degradation hooks for tests (no external chaos frameworks)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Any
from unittest import mock


@contextmanager
def redis_get_returns_none() -> Iterator[None]:
    """Simulate disconnected / unavailable Redis client (``get_redis`` → None)."""

    async def _none() -> None:
        return None

    with mock.patch("utils.redis_client.get_redis", new=_none):
        yield


@contextmanager
def redis_ping_raises() -> Iterator[None]:
    """Client exists but ping fails (health check degradation)."""

    class _Bad:
        async def ping(self) -> bool:
            raise ConnectionError("simulated_redis_ping_failure")

    async def _cli() -> Any:
        return _Bad()

    with mock.patch("utils.redis_client.get_redis", new=_cli):
        with mock.patch("utils.redis_client.redis_ping_ok", new=mock.AsyncMock(return_value=False)):
            yield


@contextmanager
def malformed_json_operational_timeline(runtime_dir: str) -> Iterator[Path]:
    from editorial.intelligence_store import operational_timeline_path

    path = operational_timeline_path(runtime_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    backup = path.read_text(encoding="utf-8") if path.is_file() else None
    path.write_text("{not json", encoding="utf-8")
    try:
        yield path
    finally:
        if backup is None:
            try:
                path.unlink()
            except OSError:
                pass
        else:
            path.write_text(backup, encoding="utf-8")


def make_stuck_job_payload(*, delivery_id: str = "stuck-soak") -> dict[str, Any]:
    return {"job_type": "SOAK", "delivery_id": delivery_id, "_stuck_marker": True}


@asynccontextmanager
async def slow_async_step(delay_sec: float) -> AsyncIterator[None]:
    """Simulate slow handler / backpressure (bounded)."""
    await asyncio.sleep(delay_sec)
    yield


def corrupt_suppression_state_partial(runtime_dir: str) -> tuple[Path, str | None]:
    """Write suppression JSON with wrong type for duplicate_burst (detectable by integrity)."""
    from editorial.intelligence_store import load_json, save_json, suppression_state_path

    path = suppression_state_path(runtime_dir)
    prev = path.read_text(encoding="utf-8") if path.is_file() else None
    base = load_json(path, {"version": 1, "entries": {}, "duplicate_burst": {}})
    base["duplicate_burst"] = "corrupt"
    save_json(path, base)
    return path, prev


def restore_text_file(path: Path, prev: str | None) -> None:
    if prev is None:
        try:
            path.unlink()
        except OSError:
            pass
    else:
        path.write_text(prev, encoding="utf-8")


# Invalid JSON for ``JobEnvelope.from_json`` negative tests.
MALFORMED_JOB_ENVELOPE = "{not_valid_json_for_job_envelope"
