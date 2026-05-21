"""Runtime paths for economics artifacts."""

from __future__ import annotations

import os
from pathlib import Path


def economics_root(runtime_dir: str | None = None) -> Path:
    base = (runtime_dir or os.getenv("RUNTIME_STATE_DIR", "var/runtime")).strip() or "var/runtime"
    p = Path(base).expanduser().resolve() / "economics"
    p.mkdir(parents=True, exist_ok=True)
    return p


def resources_hourly_path(runtime_dir: str | None = None) -> Path:
    return economics_root(runtime_dir) / "resources_hourly.json"


def resources_daily_path(runtime_dir: str | None = None) -> Path:
    return economics_root(runtime_dir) / "resources_daily.json"


def budget_state_path(runtime_dir: str | None = None) -> Path:
    return economics_root(runtime_dir) / "budget_state.json"


def throughput_state_path(runtime_dir: str | None = None) -> Path:
    return economics_root(runtime_dir) / "throughput_state.json"


def storage_state_path(runtime_dir: str | None = None) -> Path:
    return economics_root(runtime_dir) / "storage_state.json"


def economic_mode_path(runtime_dir: str | None = None) -> Path:
    return economics_root(runtime_dir) / "economic_mode.json"


def roi_daily_path(runtime_dir: str | None = None) -> Path:
    return economics_root(runtime_dir) / "roi_daily.json"


def slo_status_path(runtime_dir: str | None = None) -> Path:
    return economics_root(runtime_dir) / "slo_status.json"


def load_shedding_path(runtime_dir: str | None = None) -> Path:
    return economics_root(runtime_dir) / "load_shedding.json"
