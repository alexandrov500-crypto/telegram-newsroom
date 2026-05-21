"""Runtime paths for governance JSON stores."""

from __future__ import annotations

from pathlib import Path

from editorial.intelligence_store import _runtime_root


def decision_ledger_path(runtime_dir: str | None = None) -> Path:
    return _runtime_root(runtime_dir) / "editorial" / "decision_ledger.jsonl"


def ranking_weights_path(runtime_dir: str | None = None) -> Path:
    return _runtime_root(runtime_dir) / "editorial" / "ranking_weights.json"


def governance_rules_path(runtime_dir: str | None = None) -> Path:
    return _runtime_root(runtime_dir) / "editorial" / "governance_rules.json"


def operator_controls_path(runtime_dir: str | None = None) -> Path:
    return _runtime_root(runtime_dir) / "editorial" / "operator_controls.json"


def governance_state_path(runtime_dir: str | None = None) -> Path:
    return _runtime_root(runtime_dir) / "editorial" / "governance_state.json"


def ranking_snapshot_path(runtime_dir: str | None = None) -> Path:
    return _runtime_root(runtime_dir) / "editorial" / "last_ranking_snapshot.json"
