"""Causal-style comparisons for advisor impact (statistics layer, no ML)."""

from __future__ import annotations

from typing import Any

from app.growth_layer.statistics.confidence import bootstrap_confidence_interval
from app.growth_layer.statistics.effect_size import calculate_effect_size
from app.growth_layer.statistics.significance import compare_two_samples

_ALPHA = 0.05


def _avg(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _lift_pct(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or b <= 1e-12:
        return None
    return round((a - b) / b * 100.0, 1)


def compare_adopted_vs_ignored(
    outcome_rows: list[dict[str, Any]],
    *,
    metric: str = "actual_err",
    recommendation_type: str | None = None,
) -> dict[str, Any]:
    """Compare posts where a recommendation was adopted vs ignored."""
    rows = list(outcome_rows)
    if recommendation_type:
        rows = [r for r in rows if str(r.get("recommendation_type") or "") == recommendation_type]
    rows = [r for r in rows if r.get(metric) is not None]
    adopted = [float(r[metric]) for r in rows if bool(r.get("adopted"))]
    ignored = [float(r[metric]) for r in rows if not bool(r.get("adopted"))]
    sig = compare_two_samples(adopted, ignored, alternative="greater") if adopted and ignored else {}
    effect = calculate_effect_size(adopted, ignored)
    ci = bootstrap_confidence_interval(adopted) if adopted else {"mean": None, "ci_low": None, "ci_high": None}
    return {
        "recommendation_type": recommendation_type or "all",
        "metric": metric,
        "adopted_n": len(adopted),
        "ignored_n": len(ignored),
        "adopted_avg": round(_avg(adopted), 4) if _avg(adopted) is not None else None,
        "ignored_avg": round(_avg(ignored), 4) if _avg(ignored) is not None else None,
        "lift_pct": _lift_pct(_avg(adopted), _avg(ignored)),
        "p_value": sig.get("p_value"),
        "test": sig.get("test"),
        "effect_size": effect.get("value"),
        "effect_size_class": effect.get("classification"),
        "confidence_interval": ci,
        "statistically_significant": sig.get("p_value") is not None and float(sig["p_value"]) < _ALPHA,
    }


def compare_advice_vs_no_advice(
    validation_rows: list[dict[str, Any]],
    *,
    advice_draft_ids: set[int],
    metric: str = "actual_err",
) -> dict[str, Any]:
    """Posts that received advisor recommendations vs posts without advice."""
    final = [r for r in validation_rows if r.get(metric) is not None]
    with_advice = [float(r[metric]) for r in final if int(r.get("draft_id") or 0) in advice_draft_ids]
    without = [float(r[metric]) for r in final if int(r.get("draft_id") or 0) not in advice_draft_ids]
    sig = compare_two_samples(with_advice, without, alternative="two-sided") if with_advice and without else {}
    effect = calculate_effect_size(with_advice, without)
    return {
        "metric": metric,
        "with_advice_n": len(with_advice),
        "without_advice_n": len(without),
        "with_advice_avg": round(_avg(with_advice), 4) if _avg(with_advice) is not None else None,
        "without_advice_avg": round(_avg(without), 4) if _avg(without) is not None else None,
        "lift_pct": _lift_pct(_avg(with_advice), _avg(without)),
        "p_value": sig.get("p_value"),
        "effect_size": effect.get("value"),
        "statistically_significant": sig.get("p_value") is not None and float(sig["p_value"]) < _ALPHA,
    }


def rank_recommendations(effectiveness: dict[str, Any]) -> dict[str, Any]:
    """Rank recommendation types by effectiveness_score."""
    ranked = sorted(
        effectiveness.items(),
        key=lambda kv: (-int((kv[1] or {}).get("effectiveness_score") or 0), -int((kv[1] or {}).get("times_shown") or 0)),
    )
    return {k: v for k, v in ranked}


def _reliability_tier(score: int) -> str:
    if score >= 85:
        return "strong"
    if score >= 70:
        return "good"
    if score >= 40:
        return "moderate"
    return "weak"


def calculate_advisor_reliability(effectiveness: dict[str, Any]) -> dict[str, Any]:
    """Overall advisor reliability from validated recommendation outcomes."""
    if not effectiveness:
        return {
            "advisor_reliability": 0,
            "tier": "weak",
            "recommendations_validated": 0,
            "statistically_significant_recommendations": 0,
        }
    scores: list[float] = []
    validated = 0
    significant = 0
    for data in effectiveness.values():
        if not isinstance(data, dict):
            continue
        n = int(data.get("times_shown") or 0)
        if n < 5:
            continue
        validated += n
        if data.get("statistically_significant"):
            significant += 1
        eff = int(data.get("effectiveness_score") or 0)
        weight = min(n, 50) / 50.0
        scores.append(eff * weight + 50 * (1 - weight))

    if not scores:
        reliability = 0
    else:
        reliability = max(0, min(100, int(round(sum(scores) / len(scores)))))

    return {
        "advisor_reliability": reliability,
        "tier": _reliability_tier(reliability),
        "recommendations_validated": validated,
        "statistically_significant_recommendations": significant,
        "recommendation_types_tracked": len(effectiveness),
    }


def build_feedback_readiness(effectiveness: dict[str, Any]) -> dict[str, Any]:
    """
    Readiness data for future phases — does NOT auto-suppress recommendations.
    Lower weight when no effect or not statistically significant.
    """
    readiness: dict[str, Any] = {}
    for rtype, data in effectiveness.items():
        if not isinstance(data, dict):
            continue
        n = int(data.get("times_shown") or 0)
        sig = bool(data.get("statistically_significant"))
        err_lift = data.get("err_lift")
        weight = 1.0
        if n >= 10 and not sig:
            weight = 0.6
        if n >= 10 and err_lift is not None and float(err_lift) <= 0:
            weight = min(weight, 0.4)
        if n >= 20 and sig and err_lift is not None and float(err_lift) > 10:
            weight = 1.2
        readiness[rtype] = {
            "future_weight": round(weight, 2),
            "statistically_significant": sig,
            "times_shown": n,
            "err_lift": err_lift,
            "auto_suppress": False,
        }
    return readiness
