"""Ephemeral runtime / DB / queue isolation for deterministic tests."""

from __future__ import annotations

import uuid
from pathlib import Path

from dataclasses import replace

from app.config import Settings


def ephemeral_queue_prefix() -> str:
    """Unique Redis / in-memory queue prefix per factory call (parallel-safe)."""
    return f"nr_t_{uuid.uuid4().hex[:12]}"


def sqlite_file_url(tmp_path: Path, filename: str = "newsroom.db") -> str:
    """On-disk SQLite URL for async SQLAlchemy."""
    return f"sqlite+aiosqlite:///{tmp_path / filename}"


def ephemeral_runtime_dir(tmp_path: Path, name: str = "runtime") -> Path:
    p = tmp_path / name
    p.mkdir(parents=True, exist_ok=True)
    (p / "snapshots").mkdir(exist_ok=True)
    return p


def build_ephemeral_settings(base: Settings, tmp_path: Path, **kwargs: object) -> Settings:
    """Clone ``base`` with isolated DB file, runtime dir, and queue prefix."""
    rt = ephemeral_runtime_dir(tmp_path)
    db_url = sqlite_file_url(tmp_path, "nr.db")
    out = replace(
        base,
        database_url=db_url,
        runtime_state_dir=str(rt),
        job_queue_prefix=ephemeral_queue_prefix(),
        job_queue_max_size=100,
        redis_enabled=False,
    )
    if not kwargs:
        return out
    return replace(out, **kwargs)  # type: ignore[arg-type]
