"""Configuration — Multi-Persona Adaptive Editorial System."""

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


def mpaes_enabled() -> bool:
    return _env_bool("EDITORIAL_MPAES_LAYER", "true")


def dual_audience_min_trust() -> float:
    """Minimum combined male+female hub trust to ship in core mode."""
    return _env_float("MPAES_DUAL_AUDIENCE_MIN_TRUST", 0.52, lo=0.35, hi=0.75)


def hub_substitution_min_score() -> float:
    return _env_float("MPAES_HUB_SUBSTITUTION_MIN", 55.0, lo=40.0, hi=80.0)


def growth_aggression_level() -> str:
    raw = os.getenv("MPAES_GROWTH_AGGRESSION", "high").strip().lower()
    return raw if raw in {"low", "medium", "high"} else "high"
