"""Configuration — Global Multi-Channel Competitive Simulation."""

from __future__ import annotations

import os


def _env_bool(name: str, default: str = "true") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float, *, lo: float, hi: float) -> float:
    raw = os.getenv(name, str(default)).strip()
    try:
        return max(lo, min(hi, float(raw)))
    except ValueError:
        return default


def gmcs_enabled() -> bool:
    return _env_bool("EDITORIAL_GMCS_LAYER", "true")


def dominance_index_threshold() -> float:
    return _env_float("GMCS_DOMINANCE_INDEX", 75.0, lo=50.0, hi=95.0)


def competitive_gap_alert() -> float:
    return _env_float("GMCS_COMPETITIVE_GAP_ALERT", 0.25, lo=0.10, hi=0.50)
