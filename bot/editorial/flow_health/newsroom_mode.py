from __future__ import annotations

from typing import Any


def classify_newsroom_mode(
    *,
    funnel: dict[str, Any] | None = None,
    rhythm: dict[str, Any] | None = None,
    digest: dict[str, Any] | None = None,
    category: dict[str, Any] | None = None,
    adaptive: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Heuristic mode label for operator clarity — not a state machine."""
    try:
        if funnel is None:
            from bot.editorial.flow_health.funnel import funnel_summary

            funnel = funnel_summary()
        if rhythm is None:
            from bot.editorial.flow_health.rhythm import compute_rhythm_modulation

            rhythm = compute_rhythm_modulation()
        if digest is None:
            from bot.editorial.flow_health.digest_discipline import compute_digest_dependency

            digest = compute_digest_dependency()
        if category is None:
            from bot.editorial.flow_health.category_balance import compute_category_distribution

            category = compute_category_distribution()
        if adaptive is None:
            from bot.editorial.flow_health.adaptive import adaptive_modulation

            adaptive = adaptive_modulation()
    except Exception:
        return {"current_mode": "STABLE", "reason": "classification_failed_open"}

    starvation = funnel.get("starvation") or {}
    starving = bool(starvation.get("detected"))
    hysteresis = float((adaptive.get("relaxation") or {}).get("hysteresis_multiplier") or 0)
    recovering = starving or hysteresis > 0.15
    bursting = bool(rhythm.get("burst_detected"))
    digest_heavy = bool(digest.get("digest_heavy"))
    imbalanced = bool(category.get("imbalanced"))

    mode = "STABLE"
    reason = "within_normal_bounds"
    if digest_heavy:
        mode = "DIGEST_HEAVY"
        reason = "recovery_digests_dominating_output"
    elif imbalanced and not starving:
        mode = "IMBALANCED"
        reason = f"dominant_category_{category.get('dominant_bucket')}"
    elif bursting and not starving:
        mode = "BURSTING"
        reason = "recent_publish_burst"
    elif starving:
        mode = "STARVING"
        reason = str(starvation.get("reason") or "starvation")
    elif recovering:
        mode = "RECOVERING"
        reason = "post_starvation_hysteresis"

    return {"current_mode": mode, "reason": reason}
