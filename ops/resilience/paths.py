"""Runtime paths for resilience artifacts."""

from __future__ import annotations

import os
from pathlib import Path


def runtime_root(runtime_dir: str | None = None) -> Path:
    base = (runtime_dir or os.getenv("RUNTIME_STATE_DIR", "var/runtime")).strip() or "var/runtime"
    p = Path(base).expanduser().resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p


def publish_journal_path(runtime_dir: str | None = None) -> Path:
    return runtime_root(runtime_dir) / "publish_journal.jsonl"


def migrations_state_path(runtime_dir: str | None = None) -> Path:
    return runtime_root(runtime_dir) / "runtime_migrations.json"


def operational_mode_path(runtime_dir: str | None = None) -> Path:
    return runtime_root(runtime_dir) / "operational_mode.json"


def deployment_manifest_path(runtime_dir: str | None = None) -> Path:
    return runtime_root(runtime_dir) / "deployment_manifest.json"


def retention_audit_path(runtime_dir: str | None = None) -> Path:
    return runtime_root(runtime_dir) / "retention_audit.jsonl"


def locks_dir(runtime_dir: str | None = None) -> Path:
    d = runtime_root(runtime_dir) / "locks"
    d.mkdir(parents=True, exist_ok=True)
    return d


def snapshots_dir(runtime_dir: str | None = None) -> Path:
    d = runtime_root(runtime_dir) / "full_snapshots"
    d.mkdir(parents=True, exist_ok=True)
    return d
