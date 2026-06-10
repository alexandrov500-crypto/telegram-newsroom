"""Configuration — Channel as Product layer."""

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


def channel_product_enabled() -> bool:
    return _env_bool("EDITORIAL_CHANNEL_PRODUCT_LAYER", "true")


def viral_reference_forward_threshold() -> int:
    return _env_int("CHANNEL_PRODUCT_VIRAL_THRESHOLD", 65, lo=50, hi=90)


def share_nudge_default_enabled() -> bool:
    return _env_bool("CHANNEL_PRODUCT_SHARE_NUDGE", "true")


def open_loop_default_enabled() -> bool:
    return _env_bool("CHANNEL_PRODUCT_OPEN_LOOP", "true")


def growth_brief_auto_threshold() -> int:
    return _env_int("CHANNEL_PRODUCT_GROWTH_BRIEF_MIN", 68, lo=55, hi=85)
