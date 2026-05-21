"""Lightweight JSON persistence under ``RUNTIME_STATE_DIR`` (no vector DB)."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

_lock = threading.RLock()


def _runtime_root(runtime_dir: str | None) -> Path:
    import os

    base = (runtime_dir or os.getenv("RUNTIME_STATE_DIR", "var/runtime")).strip() or "var/runtime"
    p = Path(base).expanduser().resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p


def topic_memory_path(runtime_dir: str | None = None) -> Path:
    return _runtime_root(runtime_dir) / "topic_memory.json"


def event_history_path(runtime_dir: str | None = None) -> Path:
    return _runtime_root(runtime_dir) / "event_history.json"


def entity_stats_path(runtime_dir: str | None = None) -> Path:
    return _runtime_root(runtime_dir) / "entity_stats.json"


def editorial_policies_path(runtime_dir: str | None = None) -> Path:
    return _runtime_root(runtime_dir) / "editorial_policies.json"


def cadence_state_path(runtime_dir: str | None = None) -> Path:
    return _runtime_root(runtime_dir) / "publish_cadence.json"


def suppression_state_path(runtime_dir: str | None = None) -> Path:
    return _runtime_root(runtime_dir) / "suppression_state.json"


def drift_snapshots_path(runtime_dir: str | None = None) -> Path:
    return _runtime_root(runtime_dir) / "editorial_drift_snapshots.json"


def operational_timeline_path(runtime_dir: str | None = None) -> Path:
    return _runtime_root(runtime_dir) / "operational_timeline.json"


def load_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    with _lock:
        if not path.is_file():
            return dict(default)
        try:
            raw = path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except (OSError, json.JSONDecodeError, TypeError):
            return dict(default)
        return data if isinstance(data, dict) else dict(default)


def save_json(path: Path, data: dict[str, Any]) -> None:
    with _lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def reset_intelligence_files_for_tests(runtime_dir: str) -> None:
    from editorial.governance.ledger import reset_ledger_for_tests
    from editorial.governance.paths import (
        decision_ledger_path,
        governance_rules_path,
        governance_state_path,
        operator_controls_path,
        ranking_snapshot_path,
        ranking_weights_path,
    )

    reset_ledger_for_tests(runtime_dir)
    for p in (
        topic_memory_path(runtime_dir),
        event_history_path(runtime_dir),
        entity_stats_path(runtime_dir),
        editorial_policies_path(runtime_dir),
        cadence_state_path(runtime_dir),
        suppression_state_path(runtime_dir),
        drift_snapshots_path(runtime_dir),
        operational_timeline_path(runtime_dir),
        decision_ledger_path(runtime_dir),
        governance_rules_path(runtime_dir),
        governance_state_path(runtime_dir),
        operator_controls_path(runtime_dir),
        ranking_snapshot_path(runtime_dir),
        ranking_weights_path(runtime_dir),
    ):
        if p.is_file():
            try:
                p.unlink()
            except OSError:
                pass
