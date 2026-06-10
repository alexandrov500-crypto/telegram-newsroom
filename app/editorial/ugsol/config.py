"""Configuration — Unified Growth & Stability Orchestration Layer."""

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


def _env_int(name: str, default: int, *, lo: int, hi: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        return max(lo, min(hi, int(raw)))
    except ValueError:
        return default


def ugsol_enabled() -> bool:
    return _env_bool("EDITORIAL_UGSOL_LAYER", "true")


def max_gap_minutes() -> int:
    return _env_int("UGSOL_MAX_GAP_MINUTES", 90, lo=60, hi=180)


def target_gap_minutes() -> int:
    return _env_int("UGSOL_TARGET_GAP_MINUTES", 55, lo=30, hi=90)


def imri_dominance_threshold() -> float:
    return _env_float("UGSOL_IMRI_DOMINANCE", 80.0, lo=60.0, hi=95.0)


def imri_recovery_threshold() -> float:
    return _env_float("UGSOL_IMRI_RECOVERY", 60.0, lo=40.0, hi=75.0)


def male_hub_base_weight() -> float:
    return _env_float("UGSOL_MALE_HUB_WEIGHT", 0.55, lo=0.40, hi=0.65)


def female_hub_base_weight() -> float:
    return _env_float("UGSOL_FEMALE_HUB_WEIGHT", 0.45, lo=0.35, hi=0.60)


def flagship_per_day_max() -> int:
    return _env_int("UGSOL_FLAGSHIP_PER_DAY", 2, lo=0, hi=5)


def digest_per_day_max() -> int:
    return _env_int("UGSOL_DIGEST_PER_DAY", 2, lo=1, hi=5)
