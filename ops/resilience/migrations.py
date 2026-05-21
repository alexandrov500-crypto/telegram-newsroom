"""Idempotent runtime JSON migrations (version tracked, rollback-aware metadata)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable

from app.versioning import RUNTIME_STATE_SCHEMA_VERSION
from editorial.intelligence_store import load_json, save_json
from ops.resilience.paths import migrations_state_path

MigrationFn = Callable[[str], dict[str, Any]]


def _load_state(runtime_dir: str) -> dict[str, Any]:
    return load_json(
        migrations_state_path(runtime_dir),
        {"version": 0, "applied": [], "history": []},
    )


def _save_state(runtime_dir: str, data: dict[str, Any]) -> None:
    save_json(migrations_state_path(runtime_dir), data)


def _migrate_governance_v1(runtime_dir: str) -> dict[str, Any]:
    """Ensure editorial/ subdir markers exist."""
    root = Path(runtime_dir) / "editorial"
    root.mkdir(parents=True, exist_ok=True)
    return {"created_editorial_dir": root.is_dir()}


def _migrate_ledger_compat_v1(runtime_dir: str) -> dict[str, Any]:
    ledger = Path(runtime_dir) / "editorial" / "decision_ledger.jsonl"
    if not ledger.is_file():
        return {"skipped": "no_ledger"}
    return {"ledger_lines": sum(1 for _ in ledger.open(encoding="utf-8"))}


_REGISTRY: list[tuple[str, int, MigrationFn]] = [
    ("governance_dir_v1", 1, _migrate_governance_v1),
    ("ledger_compat_v1", 1, _migrate_ledger_compat_v1),
]


def apply_runtime_migrations(runtime_dir: str) -> dict[str, Any]:
    state = _load_state(runtime_dir)
    applied = set(state.get("applied") or [])
    results: list[dict[str, Any]] = []
    for name, target_schema, fn in _REGISTRY:
        if name in applied:
            continue
        if target_schema > RUNTIME_STATE_SCHEMA_VERSION:
            continue
        detail = fn(runtime_dir)
        applied.add(name)
        results.append({"migration": name, "detail": detail})
        hist = list(state.get("history") or [])
        hist.append({
            "migration": name,
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "detail": detail,
        })
        state["history"] = hist[-100:]
    state["applied"] = sorted(applied)
    state["target_schema_version"] = RUNTIME_STATE_SCHEMA_VERSION
    state["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    _save_state(runtime_dir, state)
    return {"applied_now": results, "state": state}


def migrations_payload(runtime_dir: str) -> dict[str, Any]:
    state = _load_state(runtime_dir)
    return {
        "runtime_state_schema_version": RUNTIME_STATE_SCHEMA_VERSION,
        "migrations_state": state,
        "registered": [{"name": n, "target_schema": s} for n, s, _ in _REGISTRY],
    }
