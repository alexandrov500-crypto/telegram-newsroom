"""Configuration — Editorial Monetization Layer."""

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


def eml_enabled() -> bool:
    return _env_bool("EDITORIAL_EML_LAYER", "true")


def min_attention_value() -> float:
    return _env_float("EML_MIN_ATTENTION_VALUE", 0.45, lo=0.20, hi=0.80)


def monetization_stress_max() -> float:
    return _env_float("EML_MONETIZATION_STRESS_MAX", 0.65, lo=0.40, hi=0.90)
