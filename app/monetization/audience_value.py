"""Audience value scoring — LTV-aware cohort segmentation (aggregate)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from app.growth.engagement_feedback import load_engagement_feedback


@dataclass(frozen=True)
class AudienceValueProfile:
    cohort: str
    ltv_score: float
    engagement_elasticity: float
    churn_risk: float
    conversion_probability: float


def _cohort_from_topic(topic_bucket: str) -> str:
    return (topic_bucket or "general").split("_")[0].lower()


def score_audience_value(
    *,
    topic_bucket: str,
    runtime_dir: str,
) -> AudienceValueProfile:
    cohort = _cohort_from_topic(topic_bucket)
    fb = load_engagement_feedback(runtime_dir)
    affinity = float(fb.vertical_weights.get(cohort, fb.global_engagement))

    ltv = round(0.35 + affinity * 0.45 + max(0.0, fb.momentum) * 0.2, 4)
    elasticity = round(0.4 + affinity * 0.35, 4)
    churn_risk = round(max(0.05, 0.55 - affinity * 0.4 - fb.momentum * 0.15), 4)
    conversion = round(min(0.85, 0.12 + affinity * 0.35 + elasticity * 0.15), 4)

    return AudienceValueProfile(
        cohort=cohort,
        ltv_score=ltv,
        engagement_elasticity=elasticity,
        churn_risk=churn_risk,
        conversion_probability=conversion,
    )


def load_cohort_monetization_map(runtime_dir: str) -> dict[str, float]:
    p = Path(runtime_dir) / "audience_value_map.json"
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return {str(k): float(v) for k, v in (data.get("ltv_by_cohort") or {}).items()}
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return {}


def save_cohort_monetization_map(runtime_dir: str, cohorts: tuple[str, ...]) -> dict[str, float]:
    mapping: dict[str, float] = {}
    for c in cohorts:
        prof = score_audience_value(topic_bucket=c, runtime_dir=runtime_dir)
        mapping[c] = prof.ltv_score
    p = Path(runtime_dir) / "audience_value_map.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"ltv_by_cohort": mapping}), encoding="utf-8")
    return mapping
