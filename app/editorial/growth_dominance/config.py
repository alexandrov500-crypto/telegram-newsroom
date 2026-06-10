"""Env configuration for Editorial Growth Dominance Layer."""

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


def egdl_enabled() -> bool:
    return _env_bool("EDITORIAL_GROWTH_DOMINANCE_LAYER", "true")


def gravity_must_publish_threshold() -> int:
    return _env_int("EGDL_GRAVITY_MUST_PUBLISH", 80, lo=70, hi=95)


def gravity_digest_only_threshold() -> int:
    return _env_int("EGDL_GRAVITY_DIGEST_ONLY", 40, lo=25, hi=55)


def gravity_reject_threshold() -> int:
    return _env_int("EGDL_GRAVITY_REJECT", 40, lo=20, hi=50)


def normal_flow_posts_max() -> int:
    return _env_int("EGDL_NORMAL_FLOW_MAX", 8, lo=4, hi=15)


def high_signal_posts_max() -> int:
    return _env_int("EGDL_HIGH_SIGNAL_MAX", 12, lo=8, hi=20)


def low_signal_posts_min() -> int:
    return _env_int("EGDL_LOW_SIGNAL_MIN", 3, lo=2, hi=8)


def require_multi_source_class() -> bool:
    return _env_bool("EGDL_REQUIRE_MULTI_SOURCE_CLASS", "true")
