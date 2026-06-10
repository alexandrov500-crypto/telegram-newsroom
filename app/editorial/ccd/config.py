"""Configuration — 7-Day Cognitive Content Design System."""

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


def ccd_enabled() -> bool:
    return _env_bool("EDITORIAL_CCD_LAYER", "true")


def daily_category_max_pct() -> float:
    return _env_float("CCD_DAILY_CATEGORY_MAX_PCT", 0.35, lo=0.25, hi=0.50)


def weekly_experience_min_fit() -> float:
    return _env_float("CCD_WEEKLY_EXPERIENCE_MIN_FIT", 0.45, lo=0.30, hi=0.70)
