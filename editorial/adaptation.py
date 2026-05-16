"""Lightweight adaptive offsets from editorial history (no online ML)."""

from __future__ import annotations

from typing import Any

from editorial.policy_models import ChannelEditorialPolicy


def adaptive_threshold_overrides(
    feedback_stats: dict[str, Any] | None,
    policy: ChannelEditorialPolicy,
) -> dict[str, Any]:
    """
    Returns numeric overrides for pipeline suppress thresholds (explainable).
    Keys: relevance_suppress_below, relevance_cooldown_update_below, duplicate_signal_suppress_above, notes.
    """
    notes: list[str] = []
    base_sup = float(policy.relevance_suppress_below)
    base_cd = float(policy.relevance_cooldown_update_below)
    base_dup = float(policy.duplicate_signal_suppress_above)
    if not feedback_stats:
        return {
            "relevance_suppress_below": base_sup,
            "relevance_cooldown_update_below": base_cd,
            "duplicate_signal_suppress_above": base_dup,
            "notes": (),
        }
    acc = float(feedback_stats.get("acceptance_proxy") or 0.5)
    pub = float((feedback_stats.get("counts") or {}).get("published") or 0)
    rej = float((feedback_stats.get("counts") or {}).get("rejected") or 0)
    sample = max(1, int(feedback_stats.get("recent_drafts_sampled") or 1))
    edits = int(feedback_stats.get("manual_edit_signals") or 0)
    edit_rate = edits / sample
    if acc < 0.52 and pub + rej > 6:
        base_sup += 4.0
        base_cd += 3.0
        notes.append("adapt_low_acceptance_raise_suppress_bar")
    if acc > 0.78 and pub + rej > 8:
        base_sup -= 2.0
        base_cd -= 2.0
        notes.append("adapt_high_acceptance_lower_suppress_bar")
    if edit_rate > 0.38:
        base_dup -= 0.06
        notes.append("adapt_high_manual_edit_duplicate_sensitivity")
    if rej > pub * 1.4 and pub + rej > 10:
        base_sup += 2.0
        notes.append("adapt_rejection_heavy_topic_scrub")
    base_sup = max(8.0, min(42.0, base_sup))
    base_cd = max(24.0, min(62.0, base_cd))
    base_dup = max(0.48, min(0.92, base_dup))
    return {
        "relevance_suppress_below": round(base_sup, 3),
        "relevance_cooldown_update_below": round(base_cd, 3),
        "duplicate_signal_suppress_above": round(base_dup, 4),
        "notes": tuple(notes),
    }
