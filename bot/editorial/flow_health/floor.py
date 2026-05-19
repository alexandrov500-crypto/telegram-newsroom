from __future__ import annotations

import os

from bot.editorial.flow_health.coverage import compute_coverage_score
from bot.editorial.flow_health.diversity import floor_diversity_allows
from bot.editorial.flow_health.funnel import funnel_summary


def _floor_enabled() -> bool:
    return os.getenv("PUBLISH_FLOOR_ENABLED", "true").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def is_publish_floor_active() -> bool:
    if not _floor_enabled():
        return False
    try:
        starvation = funnel_summary().get("starvation") or {}
        return bool(starvation.get("detected"))
    except Exception:
        return False


def should_force_cluster_enqueue(*, headline: str | None = None) -> bool:
    if not is_publish_floor_active():
        return False
    if os.getenv("PUBLISH_FLOOR_RELAX_CLUSTER", "true").strip().lower() not in (
        "1",
        "true",
        "yes",
        "on",
    ):
        return False
    if headline:
        div = floor_diversity_allows(headline)
        if not div.get("allowed", True):
            return False
    return True


def floor_allows_relaxed_publish(*, headline: str) -> dict:
    """Combined coverage + diversity gate for relaxed publish paths."""
    out: dict = {"allowed": True}
    try:
        if not is_publish_floor_active():
            out["reason"] = "floor_inactive"
            return out
        cov = compute_coverage_score()
        out["coverage"] = cov
        div = floor_diversity_allows(headline)
        out["diversity"] = div
        if not div.get("allowed", True):
            out["allowed"] = False
            out["reason"] = div.get("reason", "diversity_blocked")
        return out
    except Exception:
        return {"allowed": True, "reason": "fail_open"}


def should_relax_auto_approval() -> bool:
    return is_publish_floor_active()
