"""Configuration — Editorial AI Autonomy v2."""

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


def eaa_enabled() -> bool:
    return _env_bool("EDITORIAL_EAA_V2_LAYER", "true")


def zero_human_mode() -> bool:
    return _env_bool("EDITORIAL_ZERO_HUMAN_IN_LOOP", "false")


def min_autonomy_confidence() -> float:
    return _env_float("EAA_MIN_AUTONOMY_CONFIDENCE", 0.68, lo=0.50, hi=0.95)


def safety_envelope_strict() -> bool:
    return _env_bool("EAA_SAFETY_ENVELOPE_STRICT", "true")
