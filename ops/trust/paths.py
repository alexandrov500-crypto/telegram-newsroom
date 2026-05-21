"""Paths for trust / certification artifacts."""

from __future__ import annotations

import os
from pathlib import Path


def trust_root(runtime_dir: str | None = None) -> Path:
    base = (runtime_dir or os.getenv("RUNTIME_STATE_DIR", "var/runtime")).strip() or "var/runtime"
    p = Path(base).expanduser().resolve() / "trust"
    p.mkdir(parents=True, exist_ok=True)
    return p


def regression_report_path(runtime_dir: str | None = None) -> Path:
    return trust_root(runtime_dir) / "behavior_regression_report.json"


def regression_baseline_path(runtime_dir: str | None = None) -> Path:
    return trust_root(runtime_dir) / "behavior_regression_baseline.json"


def trust_certification_path(runtime_dir: str | None = None, *, date: str | None = None) -> Path:
    d = date or __import__("time").strftime("%Y%m%d", __import__("time").gmtime())
    return trust_root(runtime_dir) / f"trust_certification_{d}.json"


def drift_baselines_path(runtime_dir: str | None = None) -> Path:
    return trust_root(runtime_dir) / "governance_drift_baselines.json"


def canary_state_path(runtime_dir: str | None = None) -> Path:
    return trust_root(runtime_dir) / "canary_state.json"


def validation_report_path(runtime_dir: str | None = None) -> Path:
    return trust_root(runtime_dir) / "autonomous_validation_report.json"


def evolution_journal_path(runtime_dir: str | None = None) -> Path:
    return trust_root(runtime_dir) / "evolution_journal.jsonl"
