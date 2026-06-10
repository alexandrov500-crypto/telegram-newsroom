"""Env-driven configuration for editorial stability & growth layer."""

from __future__ import annotations

import os


def _env_bool(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, *, lo: int, hi: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        return max(lo, min(hi, int(raw)))
    except ValueError:
        return default


def stability_layer_enabled() -> bool:
    return _env_bool("EDITORIAL_STABILITY_LAYER", "true")


def anti_pause_gap_minutes() -> int:
    return _env_int("EDITORIAL_ANTI_PAUSE_GAP_MINUTES", 75, lo=30, hi=180)


def anti_pause_max_gap_minutes() -> int:
    return _env_int("EDITORIAL_ANTI_PAUSE_MAX_GAP_MINUTES", 90, lo=45, hi=240)


def elastic_cluster_max_age_hours() -> float:
    try:
        return max(1.0, min(12.0, float(os.getenv("EDITORIAL_ELASTIC_CLUSTER_MAX_HOURS", "6"))))
    except ValueError:
        return 6.0


def baseline_posts_per_day() -> int:
    return _env_int("EDITORIAL_BASELINE_POSTS_PER_DAY", 5, lo=3, hi=15)


def target_posts_per_day() -> int:
    return _env_int("EDITORIAL_TARGET_POSTS_PER_DAY", 8, lo=5, hi=20)


def contextual_post_min_ratio_pct() -> int:
    return _env_int("EDITORIAL_CONTEXTUAL_MIN_RATIO_PCT", 30, lo=10, hi=80)


def active_hours_start() -> int:
    return _env_int("EDITORIAL_ACTIVE_HOURS_START", 7, lo=0, hi=23)


def active_hours_end() -> int:
    return _env_int("EDITORIAL_ACTIVE_HOURS_END", 23, lo=1, hi=24)


def governance_bypass_on_anti_pause() -> bool:
    return _env_bool("EDITORIAL_STABILITY_GOV_BYPASS", "true")


def skip_cadence_cap_on_anti_pause() -> bool:
    return _env_bool("EDITORIAL_STABILITY_SKIP_CADENCE_ON_ANTI_PAUSE", "true")
