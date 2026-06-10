"""Runtime registry for recommendation policy."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.growth_layer.advisor_validation.effectiveness import evaluate_recommendation_effectiveness
from app.growth_layer.advisor_validation.reporting import load_advisor_effectiveness_snapshot
from app.growth_layer.policy.policy_scoring import PolicyTier, build_policy_record, tier_sort_key
from app.growth_layer.policy.recommendation_policy import build_global_policy, build_segment_policies, count_policies_by_tier


def build_policy_registry(
    outcome_rows: list[dict[str, Any]],
    *,
    advice_rows: list[dict[str, Any]] | None = None,
    effectiveness_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build global + segment policy registry from outcomes or cached effectiveness."""
    if effectiveness_snapshot and isinstance(effectiveness_snapshot.get("effectiveness_detail"), dict):
        effectiveness = effectiveness_snapshot["effectiveness_detail"]
    else:
        effectiveness = evaluate_recommendation_effectiveness(outcome_rows)

    recommendations = build_global_policy(effectiveness)
    segments: dict[str, Any] = {}
    if advice_rows is not None:
        segments = build_segment_policies(outcome_rows, advice_rows)

    tier_counts = count_policies_by_tier(recommendations)
    trusted = [k for k, v in recommendations.items() if v.get("tier") == PolicyTier.TRUSTED.value]
    retired = [k for k, v in recommendations.items() if v.get("tier") == PolicyTier.RETIRED.value]

    top_trusted = sorted(
        recommendations.items(),
        key=lambda kv: -int((kv[1] or {}).get("policy_score") or 0),
    )
    top_trusted = [(k, v) for k, v in top_trusted if v.get("tier") == PolicyTier.TRUSTED.value][:3]
    top_retired = [(k, v) for k, v in recommendations.items() if v.get("tier") == PolicyTier.RETIRED.value][:3]

    return {
        "recommendations": recommendations,
        "segments": segments,
        "tier_counts": tier_counts,
        "trusted_recommendations": tier_counts.get(PolicyTier.TRUSTED.value, 0),
        "experimental_recommendations": tier_counts.get(PolicyTier.EXPERIMENTAL.value, 0),
        "unverified_recommendations": tier_counts.get(PolicyTier.UNVERIFIED.value, 0),
        "retired_recommendations": tier_counts.get(PolicyTier.RETIRED.value, 0),
        "top_trusted": [{"type": k, **v} for k, v in top_trusted],
        "top_retired": [{"type": k, **v} for k, v in top_retired],
        "trusted_types": trusted,
        "retired_types": retired,
    }


def persist_policy_registry(runtime_dir: str | Path, registry: dict[str, Any]) -> dict[str, Any]:
    path = Path(runtime_dir) / "recommendation_policy.json"
    slim = {
        k: registry.get(k)
        for k in ("recommendations", "segments", "tier_counts", "trusted_recommendations", "experimental_recommendations", "unverified_recommendations", "retired_recommendations", "top_trusted", "top_retired")
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(slim, ensure_ascii=False, indent=2), encoding="utf-8")
    return slim


def load_policy_registry(runtime_dir: str | Path | None = None) -> dict[str, Any]:
    if runtime_dir is None:
        return {"recommendations": {}, "segments": {}}
    path = Path(runtime_dir) / "recommendation_policy.json"
    if not path.is_file():
        eff = load_advisor_effectiveness_snapshot(runtime_dir)
        if eff and isinstance(eff.get("effectiveness_detail"), dict):
            return build_policy_registry([], effectiveness_snapshot=eff)
        return {"recommendations": {}, "segments": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data.setdefault("recommendations", {})
            data.setdefault("segments", {})
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return {"recommendations": {}, "segments": {}}


def enrich_advisor_reliability(
    registry: dict[str, Any],
    *,
    base_reliability: int | None = None,
) -> dict[str, Any]:
    """Extended advisor reliability breakdown (Part 10)."""
    recs = registry.get("recommendations") if isinstance(registry.get("recommendations"), dict) else {}
    trusted_scores = [int(v.get("policy_score") or 0) for v in recs.values() if v.get("tier") == PolicyTier.TRUSTED.value]
    if base_reliability is None:
        if trusted_scores:
            base_reliability = int(round(sum(trusted_scores) / len(trusted_scores)))
        else:
            base_reliability = 0
    return {
        "advisor_reliability": max(0, min(100, int(base_reliability))),
        "trusted_recommendations": int(registry.get("trusted_recommendations") or 0),
        "experimental_recommendations": int(registry.get("experimental_recommendations") or 0),
        "unverified_recommendations": int(registry.get("unverified_recommendations") or 0),
        "retired_recommendations": int(registry.get("retired_recommendations") or 0),
    }
