"""Rules for switching NEWSROOM_PUBLISH_FORMAT based on measured lift + significance."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from app.growth_layer.statistics.decision_metrics import (
    DecisionReliabilityVerdict,
    evaluate_decision_reliability,
)

ConfidenceLevel = Literal["LOW", "MEDIUM", "HIGH"]


@dataclass(frozen=True)
class FormatDecisionVerdict:
    recommended_format: str
    recommended_mode: str
    confidence: ConfidenceLevel
    sample_size: int
    reason: str
    cb_sample: int
    growth_sample: int
    cb_avg_err: float | None
    growth_avg_err: float | None
    cb_avg_forward_rate: float | None
    growth_avg_forward_rate: float | None
    err_lift_pct: float | None
    forward_lift_pct: float | None
    meets_threshold: bool
    statistically_significant: bool = False
    err_p_value: float | None = None
    forward_p_value: float | None = None
    effect_size: str = "unknown"
    err_effect_size: dict[str, Any] = field(default_factory=dict)
    forward_effect_size: dict[str, Any] = field(default_factory=dict)
    stability: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "recommended_format": self.recommended_format,
            "recommended_mode": self.recommended_mode,
            "confidence": self.confidence,
            "sample_size": self.sample_size,
            "reason": self.reason,
            "cb_sample": self.cb_sample,
            "growth_sample": self.growth_sample,
            "cb_avg_err": self.cb_avg_err,
            "growth_avg_err": self.growth_avg_err,
            "cb_avg_forward_rate": self.cb_avg_forward_rate,
            "growth_avg_forward_rate": self.growth_avg_forward_rate,
            "err_lift_pct": self.err_lift_pct,
            "forward_lift_pct": self.forward_lift_pct,
            "meets_threshold": self.meets_threshold,
            "statistically_significant": self.statistically_significant,
            "err_p_value": self.err_p_value,
            "forward_p_value": self.forward_p_value,
            "effect_size": self.effect_size,
            "err_effect_size": dict(self.err_effect_size),
            "forward_effect_size": dict(self.forward_effect_size),
            "stability": dict(self.stability),
        }


def _from_reliability(v: DecisionReliabilityVerdict) -> FormatDecisionVerdict:
    cmp = v.comparison or {}
    return FormatDecisionVerdict(
        recommended_format=v.recommended_format,
        recommended_mode=v.recommended_mode,
        confidence=v.confidence,
        sample_size=v.sample_size,
        reason=v.reason,
        cb_sample=v.cb_sample,
        growth_sample=v.growth_sample,
        cb_avg_err=cmp.get("cb_mean_err"),
        growth_avg_err=cmp.get("growth_mean_err"),
        cb_avg_forward_rate=cmp.get("cb_mean_forwards"),
        growth_avg_forward_rate=cmp.get("growth_mean_forwards"),
        err_lift_pct=v.err_lift_pct,
        forward_lift_pct=v.forward_lift_pct,
        meets_threshold=v.meets_threshold,
        statistically_significant=v.statistically_significant,
        err_p_value=v.err_p_value,
        forward_p_value=v.forward_p_value,
        effect_size=v.effect_size,
        err_effect_size=v.err_effect_size,
        forward_effect_size=v.forward_effect_size,
        stability=v.stability,
    )


def evaluate_format_decision(rows: list[dict[str, Any]], *, final_only: bool = True) -> FormatDecisionVerdict:
    """Statistical guardrails + significance tests for format recommendation."""
    return _from_reliability(evaluate_decision_reliability(rows, final_only=final_only))
