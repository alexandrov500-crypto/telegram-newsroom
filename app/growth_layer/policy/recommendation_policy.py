"""Recommendation policy rules and application to advisor output."""

from __future__ import annotations

from typing import Any

from app.growth_layer.advisor_validation.adoption import recommendation_type_for_feature
from app.growth_layer.advisor_validation.effectiveness import evaluate_recommendation_effectiveness
from app.growth_layer.policy.policy_scoring import PolicyTier, build_policy_record, tier_sort_key

MAX_RECOMMENDATIONS = 5
_DEFAULT_TIER = PolicyTier.UNVERIFIED.value
_EXCLUDE_BY_DEFAULT = {PolicyTier.RETIRED.value}


def build_global_policy(effectiveness: dict[str, Any]) -> dict[str, Any]:
    policies: dict[str, Any] = {}
    for rtype, row in effectiveness.items():
        if isinstance(row, dict):
            policies[str(rtype)] = build_policy_record(row)
    return policies


def build_segment_policies(
    outcome_rows: list[dict[str, Any]],
    advice_rows: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Per-segment policy from outcomes joined with advice predicted_segment."""
    by_draft = {int(r["draft_id"]): r for r in advice_rows if r.get("draft_id") is not None}
    by_segment: dict[str, list[dict[str, Any]]] = {}
    for row in outcome_rows:
        draft_id = int(row.get("draft_id") or 0)
        advice = by_draft.get(draft_id) or {}
        segment = str(advice.get("predicted_segment") or row.get("segment") or "general_news")
        by_segment.setdefault(segment, []).append(dict(row))

    segment_policies: dict[str, dict[str, Any]] = {}
    for segment, rows in by_segment.items():
        eff = evaluate_recommendation_effectiveness(rows)
        segment_policies[segment] = build_global_policy(eff)
    return segment_policies


def resolve_policy_for_type(
    recommendation_type: str,
    *,
    registry: dict[str, Any],
    segment: str | None = None,
) -> dict[str, Any]:
    """Segment policy overrides global when present."""
    normalized = str(recommendation_type or "")
    seg = str(segment or "").strip().lower()
    segments = registry.get("segments") if isinstance(registry.get("segments"), dict) else {}
    if seg and seg in segments:
        seg_policy = segments[seg]
        if isinstance(seg_policy, dict) and normalized in seg_policy:
            return dict(seg_policy[normalized])
    global_policy = registry.get("recommendations") if isinstance(registry.get("recommendations"), dict) else {}
    if normalized in global_policy:
        return dict(global_policy[normalized])
    return {
        "recommendation_type": normalized,
        "tier": _DEFAULT_TIER,
        "policy_score": 50,
        "confidence": "LOW",
    }


def apply_recommendation_policy(
    raw: dict[str, Any],
    *,
    registry: dict[str, Any],
    segment: str | None = None,
    max_recommendations: int = MAX_RECOMMENDATIONS,
) -> dict[str, Any]:
    """
    Sort, tier-label, and limit recommendations using policy registry.
    RETIRED recommendations excluded by default (not deleted).
    """
    detailed = list(raw.get("recommendations_detailed") or [])
    mismatches = list(raw.get("mismatches") or [])
    if not detailed:
        return raw

    enriched: list[dict[str, Any]] = []
    for item in detailed:
        if not isinstance(item, dict):
            continue
        feature = str(item.get("feature") or "")
        rec_type = recommendation_type_for_feature(feature) if feature else str(item.get("recommendation_type") or "")
        policy = resolve_policy_for_type(rec_type, registry=registry, segment=segment)
        tier = str(policy.get("tier") or _DEFAULT_TIER)
        if tier in _EXCLUDE_BY_DEFAULT:
            continue
        enriched.append(
            {
                **item,
                "recommendation_type": rec_type,
                "tier": tier,
                "policy_score": int(policy.get("policy_score") or 50),
                "confidence": policy.get("confidence"),
                "policy": policy,
            }
        )

    enriched.sort(key=lambda x: (tier_sort_key(str(x.get("tier"))), -int(x.get("policy_score") or 0)))
    selected = enriched[: max(1, int(max_recommendations))]

    recommendations: list[str] = []
    selected_mismatches: list[dict[str, Any]] = []
    mismatch_by_feature = {str(m.get("feature")): m for m in mismatches if isinstance(m, dict)}

    for item in selected:
        action = str(item.get("text") or "")
        tier = str(item.get("tier") or _DEFAULT_TIER)
        evidence = str(item.get("evidence") or "")
        recommendations.append(f"{action} ({tier}) — {evidence}" if evidence else f"{action} ({tier})")
        feat = str(item.get("feature") or "")
        if feat in mismatch_by_feature:
            selected_mismatches.append(mismatch_by_feature[feat])

    return {
        **raw,
        "recommendations": recommendations,
        "recommendations_detailed": selected,
        "mismatches": selected_mismatches or mismatches[:max_recommendations],
        "policy_applied": True,
        "policy_segment": segment,
    }


def count_policies_by_tier(policies: dict[str, Any]) -> dict[str, int]:
    counts = {PolicyTier.TRUSTED.value: 0, PolicyTier.EXPERIMENTAL.value: 0, PolicyTier.UNVERIFIED.value: 0, PolicyTier.RETIRED.value: 0}
    for data in policies.values():
        if not isinstance(data, dict):
            continue
        tier = str(data.get("tier") or _DEFAULT_TIER).upper()
        if tier in counts:
            counts[tier] += 1
    return counts
