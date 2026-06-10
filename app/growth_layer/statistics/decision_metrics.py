"""Format comparison metrics and decision reliability for Growth Validation."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Literal

from app.growth_layer.statistics.effect_size import calculate_effect_size, effect_size_meets_minimum
from app.growth_layer.statistics.significance import compare_two_samples
from app.growth_layer.validation.status import filter_final_rows

ConfidenceLevel = Literal["LOW", "MEDIUM", "HIGH"]

_METRIC_KEYS = {
    "err": "actual_err",
    "forwards": "actual_forward_rate",
    "engagement": "actual_engagement",
    "acquisition_proxy_score": "acquisition_proxy_score",
}


def _min_total() -> int:
    try:
        return max(10, int(os.getenv("GROWTH_FORMAT_DECISION_MIN_SAMPLE", "50")))
    except ValueError:
        return 50


def _min_cohort() -> int:
    try:
        return max(3, int(os.getenv("GROWTH_FORMAT_DECISION_MIN_COHORT", "20")))
    except ValueError:
        return 20


def _alpha() -> float:
    try:
        return float(os.getenv("GROWTH_STAT_SIGNIFICANCE_ALPHA", "0.05"))
    except ValueError:
        return 0.05


def _confidence(sample_size: int) -> ConfidenceLevel:
    if sample_size >= 250:
        return "HIGH"
    if sample_size >= 100:
        return "MEDIUM"
    return "LOW"


def _extract_values(rows: list[dict[str, Any]], metric: str) -> list[float]:
    key = _METRIC_KEYS[metric]
    out: list[float] = []
    for r in rows:
        if metric == "acquisition_proxy_score":
            from app.growth_layer.validation.acquisition_proxy import acquisition_proxy_score

            out.append(float(acquisition_proxy_score(r)))
        elif r.get(key) is not None:
            out.append(float(r[key]))
    return out


def _mean(vals: list[float]) -> float | None:
    if not vals:
        return None
    return sum(vals) / len(vals)


def _lift_pct(growth_val: float | None, cb_val: float | None) -> float | None:
    if growth_val is None or cb_val is None or cb_val <= 1e-9:
        return None
    return round((growth_val - cb_val) / cb_val * 100.0, 2)


def _metric_comparison(
    growth_rows: list[dict[str, Any]],
    cb_rows: list[dict[str, Any]],
    metric: str,
) -> dict[str, Any]:
    g_vals = _extract_values(growth_rows, metric)
    c_vals = _extract_values(cb_rows, metric)
    g_mean = _mean(g_vals)
    c_mean = _mean(c_vals)
    sig = compare_two_samples(g_vals, c_vals, alternative="greater")
    effect = calculate_effect_size(g_vals, c_vals)
    return {
        "growth_mean": round(g_mean, 4) if g_mean is not None else None,
        "cb_mean": round(c_mean, 4) if c_mean is not None else None,
        "lift_pct": _lift_pct(g_mean, c_mean),
        "p_value": sig.get("p_value"),
        "test": sig.get("test"),
        "effect_size": effect,
        "warnings": sig.get("warnings") or [],
    }


def compare_content_formats(
    growth_posts: list[dict[str, Any]],
    cb_posts: list[dict[str, Any]],
) -> dict[str, Any]:
    """Statistical comparison of Growth Brief vs CB Brief cohorts."""
    err = _metric_comparison(growth_posts, cb_posts, "err")
    forwards = _metric_comparison(growth_posts, cb_posts, "forwards")
    engagement = _metric_comparison(growth_posts, cb_posts, "engagement")
    acquisition = _metric_comparison(growth_posts, cb_posts, "acquisition_proxy_score")

    warnings: list[str] = []
    for block in (err, forwards, engagement, acquisition):
        for w in block.get("warnings") or []:
            if w not in warnings:
                warnings.append(w)

    return {
        "growth_mean_err": err["growth_mean"],
        "cb_mean_err": err["cb_mean"],
        "growth_mean_forwards": forwards["growth_mean"],
        "cb_mean_forwards": forwards["cb_mean"],
        "growth_mean_engagement": engagement["growth_mean"],
        "cb_mean_engagement": engagement["cb_mean"],
        "growth_mean_acquisition_proxy": acquisition["growth_mean"],
        "cb_mean_acquisition_proxy": acquisition["cb_mean"],
        "err_lift_pct": err["lift_pct"],
        "forward_lift_pct": forwards["lift_pct"],
        "engagement_lift_pct": engagement["lift_pct"],
        "acquisition_lift_pct": acquisition["lift_pct"],
        "err_p_value": err["p_value"],
        "forward_p_value": forwards["p_value"],
        "engagement_p_value": engagement["p_value"],
        "acquisition_p_value": acquisition["p_value"],
        "err_effect_size": err["effect_size"],
        "forward_effect_size": forwards["effect_size"],
        "engagement_effect_size": engagement["effect_size"],
        "acquisition_effect_size": acquisition["effect_size"],
        "err_test": err["test"],
        "forward_test": forwards["test"],
        "warnings": warnings,
        "growth_sample": len(growth_posts),
        "cb_sample": len(cb_posts),
    }


@dataclass(frozen=True)
class DecisionReliabilityVerdict:
    recommended_mode: str
    recommended_format: str
    confidence: ConfidenceLevel
    sample_size: int
    cb_sample: int
    growth_sample: int
    reason: str
    statistically_significant: bool
    meets_threshold: bool
    err_lift_pct: float | None
    forward_lift_pct: float | None
    err_p_value: float | None
    forward_p_value: float | None
    effect_size: str
    err_effect_size: dict[str, Any]
    forward_effect_size: dict[str, Any]
    comparison: dict[str, Any] = field(default_factory=dict)
    stability: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "recommended_mode": self.recommended_mode,
            "recommended_format": self.recommended_format,
            "confidence": self.confidence,
            "sample_size": self.sample_size,
            "cb_sample": self.cb_sample,
            "growth_sample": self.growth_sample,
            "reason": self.reason,
            "statistically_significant": self.statistically_significant,
            "meets_threshold": self.meets_threshold,
            "err_lift_pct": self.err_lift_pct,
            "forward_lift_pct": self.forward_lift_pct,
            "err_p_value": self.err_p_value,
            "forward_p_value": self.forward_p_value,
            "effect_size": self.effect_size,
            "err_effect_size": dict(self.err_effect_size),
            "forward_effect_size": dict(self.forward_effect_size),
            "comparison": dict(self.comparison),
            "stability": dict(self.stability),
        }


def _primary_effect_label(err_es: dict[str, Any], forward_es: dict[str, Any]) -> str:
    order = {"negligible": 0, "unknown": -1, "small": 1, "medium": 2, "large": 3}
    err_c = str(err_es.get("classification") or "unknown")
    fwd_c = str(forward_es.get("classification") or "unknown")
    return err_c if order.get(err_c, -1) <= order.get(fwd_c, -1) else fwd_c


def build_stability_analysis(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Compare format lift across last 30, last 90, and all-time windows."""
    windows = {
        "last_30": rows[:30],
        "last_90": rows[:90],
        "all_time": rows,
    }
    out: dict[str, Any] = {}
    for name, window_rows in windows.items():
        validated = filter_final_rows(window_rows)
        cb_rows = [r for r in validated if str(r.get("format_profile") or "") == "cb_brief"]
        growth_rows = [r for r in validated if str(r.get("format_profile") or "") == "growth_brief"]
        if len(growth_rows) < 2 or len(cb_rows) < 2:
            out[name] = {
                "sample_size": len(validated),
                "growth_sample": len(growth_rows),
                "cb_sample": len(cb_rows),
                "err_lift_pct": None,
                "forward_lift_pct": None,
                "err_p_value": None,
                "forward_p_value": None,
                "effect_size": "unknown",
                "statistically_significant": False,
            }
            continue
        cmp = compare_content_formats(growth_rows, cb_rows)
        err_es = cmp.get("err_effect_size") or {}
        fr_es = cmp.get("forward_effect_size") or {}
        alpha = _alpha()
        sig = (
            cmp.get("err_p_value") is not None
            and cmp.get("forward_p_value") is not None
            and cmp["err_p_value"] < alpha
            and cmp["forward_p_value"] < alpha
            and effect_size_meets_minimum(str(err_es.get("classification") or ""))
            and effect_size_meets_minimum(str(fr_es.get("classification") or ""))
        )
        out[name] = {
            "sample_size": len(validated),
            "growth_sample": len(growth_rows),
            "cb_sample": len(cb_rows),
            "err_lift_pct": cmp.get("err_lift_pct"),
            "forward_lift_pct": cmp.get("forward_lift_pct"),
            "err_p_value": cmp.get("err_p_value"),
            "forward_p_value": cmp.get("forward_p_value"),
            "effect_size": _primary_effect_label(err_es, fr_es),
            "statistically_significant": bool(sig),
        }
    return out


def _evaluate_from_cohorts(
    *,
    validated: list[dict[str, Any]],
    growth_rows: list[dict[str, Any]],
    cb_rows: list[dict[str, Any]],
    include_stability: bool,
) -> DecisionReliabilityVerdict:
    min_total = _min_total()
    min_cohort = _min_cohort()
    alpha = _alpha()
    sample_size = len(validated)
    confidence = _confidence(sample_size)
    comparison = compare_content_formats(growth_rows, cb_rows)

    err_lift = comparison.get("err_lift_pct")
    fr_lift = comparison.get("forward_lift_pct")
    err_p = comparison.get("err_p_value")
    fr_p = comparison.get("forward_p_value")
    err_es = comparison.get("err_effect_size") or {}
    fr_es = comparison.get("forward_effect_size") or {}
    effect_label = _primary_effect_label(err_es, fr_es)

    guardrails_ok = (
        sample_size >= min_total
        and len(growth_rows) >= min_cohort
        and len(cb_rows) >= min_cohort
    )
    lift_ok = (
        err_lift is not None
        and fr_lift is not None
        and err_lift >= 10.0
        and fr_lift >= 15.0
    )
    significance_ok = (
        err_p is not None
        and fr_p is not None
        and err_p < alpha
        and fr_p < alpha
    )
    effect_ok = effect_size_meets_minimum(str(err_es.get("classification") or "")) and effect_size_meets_minimum(
        str(fr_es.get("classification") or "")
    )
    statistically_significant = bool(guardrails_ok and lift_ok and significance_ok and effect_ok)
    meets = statistically_significant

    stability: dict[str, Any] = {}
    if include_stability:
        stability = build_stability_analysis(validated)

    if meets:
        return DecisionReliabilityVerdict(
            recommended_mode="growth_brief",
            recommended_format="growth_brief",
            confidence=confidence,
            sample_size=sample_size,
            cb_sample=len(cb_rows),
            growth_sample=len(growth_rows),
            reason="growth_brief_statistically_outperforms_cb",
            statistically_significant=True,
            meets_threshold=True,
            err_lift_pct=err_lift,
            forward_lift_pct=fr_lift,
            err_p_value=err_p,
            forward_p_value=fr_p,
            effect_size=effect_label,
            err_effect_size=err_es,
            forward_effect_size=fr_es,
            comparison=comparison,
            stability=stability,
        )

    reason = "not_statistically_significant"
    if sample_size < min_total:
        reason = f"validated_sample_below_{min_total}"
    elif len(growth_rows) < min_cohort:
        reason = "insufficient_treatment_group"
    elif len(cb_rows) < min_cohort:
        reason = "insufficient_control_group"
    elif err_lift is not None and err_lift < 10.0:
        reason = "err_lift_below_10pct"
    elif fr_lift is not None and fr_lift < 15.0:
        reason = "forward_lift_below_15pct"
    elif not significance_ok:
        reason = "not_statistically_significant"
    elif not effect_ok:
        reason = "effect_size_below_small"

    return DecisionReliabilityVerdict(
        recommended_mode="hybrid",
        recommended_format="hybrid",
        confidence=confidence,
        sample_size=sample_size,
        cb_sample=len(cb_rows),
        growth_sample=len(growth_rows),
        reason=reason,
        statistically_significant=False,
        meets_threshold=False,
        err_lift_pct=err_lift,
        forward_lift_pct=fr_lift,
        err_p_value=err_p,
        forward_p_value=fr_p,
        effect_size=effect_label,
        err_effect_size=err_es,
        forward_effect_size=fr_es,
        comparison=comparison,
        stability=stability,
    )


def evaluate_decision_reliability(
    rows: list[dict[str, Any]],
    *,
    final_only: bool = True,
    include_stability: bool = True,
) -> DecisionReliabilityVerdict:
    """Full statistical decision layer on FINAL validation rows."""
    validated = filter_final_rows(rows) if final_only else [r for r in rows if r.get("actual_engagement") is not None]
    cb_rows = [r for r in validated if str(r.get("format_profile") or "") == "cb_brief"]
    growth_rows = [r for r in validated if str(r.get("format_profile") or "") == "growth_brief"]
    return _evaluate_from_cohorts(
        validated=validated,
        growth_rows=growth_rows,
        cb_rows=cb_rows,
        include_stability=include_stability,
    )
