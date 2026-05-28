"""Runtime artifact paths for ops pipeline layer."""

from __future__ import annotations

import os
from pathlib import Path


def runtime_root(runtime_dir: str | None = None) -> Path:
    base = (runtime_dir or os.getenv("RUNTIME_STATE_DIR", "var/runtime")).strip() or "var/runtime"
    p = Path(base).expanduser().resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p


def ingestion_ledger_path(runtime_dir: str | None = None) -> Path:
    return runtime_root(runtime_dir) / "ledger.jsonl"


def dedup_index_path(runtime_dir: str | None = None) -> Path:
    return runtime_root(runtime_dir) / "dedup_index.jsonl"


def checkpoint_latest_path(runtime_dir: str | None = None) -> Path:
    checkpoints = runtime_root(runtime_dir) / "checkpoints"
    checkpoints.mkdir(parents=True, exist_ok=True)
    return checkpoints / "latest.json"


def pipeline_state_path(runtime_dir: str | None = None) -> Path:
    return runtime_root(runtime_dir) / "pipeline_state.jsonl"


def scored_items_path(runtime_dir: str | None = None) -> Path:
    return runtime_root(runtime_dir) / "scored_items.jsonl"


def events_ndjson_path(runtime_dir: str | None = None) -> Path:
    return runtime_root(runtime_dir) / "events.ndjson"


def idempotency_index_path(runtime_dir: str | None = None) -> Path:
    return runtime_root(runtime_dir) / "idempotency_index.jsonl"


def source_health_path(runtime_dir: str | None = None) -> Path:
    return runtime_root(runtime_dir) / "source_health.json"
