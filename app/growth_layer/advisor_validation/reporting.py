"""Advisor effectiveness reporting and runtime snapshots."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.growth_layer.advisor_validation.causal_analysis import (
    build_feedback_readiness,
    calculate_advisor_reliability,
    compare_advice_vs_no_advice,
    compare_adopted_vs_ignored,
    rank_recommendations,
)
from app.growth_layer.advisor_validation.effectiveness import evaluate_recommendation_effectiveness


def build_advisor_effectiveness_snapshot(
    outcome_rows: list[dict[str, Any]],
    *,
    validation_rows: list[dict[str, Any]] | None = None,
    advice_draft_ids: set[int] | None = None,
) -> dict[str, Any]:
    effectiveness = evaluate_recommendation_effectiveness(outcome_rows)
    ranked = rank_recommendations(effectiveness)
    reliability = calculate_advisor_reliability(effectiveness)
    feedback = build_feedback_readiness(effectiveness)

    recommendations_shown = len(outcome_rows)
    adopted_count = sum(1 for r in outcome_rows if bool(r.get("adopted")))
    adoption_rate = round(adopted_count / recommendations_shown * 100.0, 1) if recommendations_shown else 0.0

    top_rec = None
    top_data = None
    if ranked:
        top_rec, top_data = next(iter(ranked.items()))

    advice_compare: dict[str, Any] = {}
    if validation_rows is not None and advice_draft_ids is not None:
        advice_compare = {
            "err": compare_advice_vs_no_advice(validation_rows, advice_draft_ids=advice_draft_ids, metric="actual_err"),
            "forwards": compare_advice_vs_no_advice(
                validation_rows, advice_draft_ids=advice_draft_ids, metric="actual_forwards"
            ),
            "engagement": compare_advice_vs_no_advice(
                validation_rows, advice_draft_ids=advice_draft_ids, metric="actual_engagement"
            ),
        }

    adopted_vs_ignored = compare_adopted_vs_ignored(outcome_rows, recommendation_type=top_rec) if top_rec else {}

    policy_registry: dict[str, Any] = {}
    try:
        from app.growth_layer.policy.policy_registry import build_policy_registry, enrich_advisor_reliability

        policy_registry = build_policy_registry(outcome_rows, effectiveness_snapshot={"effectiveness_detail": effectiveness})
        reliability_ext = enrich_advisor_reliability(policy_registry, base_reliability=reliability.get("advisor_reliability"))
    except Exception:
        reliability_ext = {
            "advisor_reliability": reliability.get("advisor_reliability"),
            "trusted_recommendations": 0,
            "experimental_recommendations": 0,
            "retired_recommendations": 0,
        }

    return {
        "advisor_reliability": reliability_ext.get("advisor_reliability"),
        "reliability_tier": reliability.get("tier"),
        "trusted_recommendations": reliability_ext.get("trusted_recommendations", 0),
        "experimental_recommendations": reliability_ext.get("experimental_recommendations", 0),
        "unverified_recommendations": reliability_ext.get("unverified_recommendations", 0),
        "retired_recommendations": reliability_ext.get("retired_recommendations", 0),
        "recommendations_validated": reliability.get("recommendations_validated"),
        "statistically_significant_recommendations": reliability.get("statistically_significant_recommendations"),
        "recommendations_shown": recommendations_shown,
        "adoption_rate": adoption_rate,
        "top_recommendation": top_rec,
        "top_recommendation_data": top_data,
        "recommendations": {
            k: {
                "adoption_rate": v.get("adoption_rate"),
                "effectiveness_score": v.get("effectiveness_score"),
                "err_lift": v.get("err_lift"),
                "p_value": v.get("p_value"),
                "statistically_significant": v.get("statistically_significant"),
            }
            for k, v in ranked.items()
        },
        "effectiveness_detail": effectiveness,
        "advice_vs_no_advice": advice_compare,
        "top_adopted_vs_ignored": adopted_vs_ignored,
        "feedback_readiness": feedback,
        "policy_summary": {
            "trusted_recommendations": reliability_ext.get("trusted_recommendations", 0),
            "experimental_recommendations": reliability_ext.get("experimental_recommendations", 0),
            "retired_recommendations": reliability_ext.get("retired_recommendations", 0),
        },
    }


def persist_advisor_effectiveness_snapshot(
    runtime_dir: str | Path,
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    path = Path(runtime_dir) / "advisor_effectiveness.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    return snapshot


def load_advisor_effectiveness_snapshot(runtime_dir: str | Path) -> dict[str, Any]:
    path = Path(runtime_dir) / "advisor_effectiveness.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}
