"""Configuration for Audience Unification Layer."""

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


def auh_enabled() -> bool:
    return _env_bool("EDITORIAL_AUDIENCE_UNIFICATION_LAYER", "true")


def ues_publish_immediate_threshold() -> int:
    return _env_int("AUH_UES_PUBLISH_IMMEDIATE", 82, lo=70, hi=95)


def ues_normal_publish_threshold() -> int:
    return _env_int("AUH_UES_NORMAL_PUBLISH", 70, lo=55, hi=85)


def ues_digest_threshold() -> int:
    return _env_int("AUH_UES_DIGEST", 55, lo=40, hi=70)


def crs_flagship_threshold() -> int:
    return _env_int("AUH_CRS_FLAGSHIP", 85, lo=75, hi=95)
