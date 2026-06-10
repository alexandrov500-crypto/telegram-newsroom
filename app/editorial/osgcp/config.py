"""Configuration — Operational Stability & Growth Control Plane."""

from __future__ import annotations

import os


def _env_bool(name: str, default: str = "true") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, *, lo: int, hi: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        return max(lo, min(hi, int(raw)))
    except ValueError:
        return default


def _env_float(name: str, default: float, *, lo: float, hi: float) -> float:
    raw = os.getenv(name, str(default)).strip()
    try:
        return max(lo, min(hi, float(raw)))
    except ValueError:
        return default


def osgcp_enabled() -> bool:
    return _env_bool("EDITORIAL_OSGCP", "true")


def max_gap_minutes() -> float:
    return _env_float("OSGCP_MAX_GAP_MINUTES", 90.0, lo=60.0, hi=180.0)


def target_gap_minutes() -> float:
    return _env_float("OSGCP_TARGET_GAP_MINUTES", 55.0, lo=30.0, hi=90.0)


def anti_pause_gap_trigger() -> float:
    return _env_float("OSGCP_ANTI_PAUSE_GAP", 75.0, lo=45.0, hi=120.0)


def gravity_signal_threshold() -> float:
    return _env_float("OSGCP_GRAVITY_SIGNAL", 80.0, lo=70.0, hi=95.0)


def gravity_low_threshold() -> float:
    return _env_float("OSGCP_GRAVITY_LOW", 50.0, lo=35.0, hi=60.0)


def mode_max_daily_pct() -> float:
    return _env_float("OSGCP_MODE_MAX_PCT", 0.45, lo=0.30, hi=0.70)


def attention_buffer_size() -> int:
    return _env_int("OSGCP_ATTENTION_BUFFER_SIZE", 20, lo=5, hi=50)
