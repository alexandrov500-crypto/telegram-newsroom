"""Configuration for Unified Editorial Operating System (UEOS)."""

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


def ueos_enabled() -> bool:
    return _env_bool("EDITORIAL_UNIFIED_OPERATING_SYSTEM", "true")


def ueos_flagship_threshold() -> int:
    return _env_int("UEOS_FLAGSHIP_THRESHOLD", 88, lo=80, hi=95)


def ueos_publish_threshold() -> int:
    return _env_int("UEOS_PUBLISH_THRESHOLD", 78, lo=65, hi=90)


def ueos_digest_threshold() -> int:
    return _env_int("UEOS_DIGEST_THRESHOLD", 65, lo=50, hi=80)


def ueos_stability_fallback_threshold() -> int:
    return _env_int("UEOS_STABILITY_FALLBACK", 50, lo=40, hi=65)


def ueos_min_channel_replacement() -> int:
    return _env_int("UEOS_MIN_CHANNEL_REPLACEMENT", 3, lo=2, hi=10)
