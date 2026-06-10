"""Configuration — Productized Editorial OS (PEOS)."""

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


def product_os_enabled() -> bool:
    return _env_bool("EDITORIAL_PRODUCT_OS", "true")


def pg_flagship_threshold() -> int:
    return _env_int("PEOS_PG_FLAGSHIP", 85, lo=75, hi=95)


def pg_publish_threshold() -> int:
    return _env_int("PEOS_PG_PUBLISH", 70, lo=55, hi=85)


def pg_digest_threshold() -> int:
    return _env_int("PEOS_PG_DIGEST", 55, lo=40, hi=70)


def cse_min_channels() -> int:
    return _env_int("PEOS_CSE_MIN_CHANNELS", 3, lo=2, hi=10)
