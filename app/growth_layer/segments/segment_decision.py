"""Segment-level format strategy decisions and stability."""

from __future__ import annotations

import os
from typing import Any, Literal

from app.growth_layer.segments.segment_statistics import _segment_performance_block
from app.growth_layer.statistics.decision_metrics import compare_content_formats
from app.growth_layer.statistics.effect_size import effect_size_meets_minimum
from app.growth_layer.statistics.significance import compare_two_samples
from app.growth_layer.validation.status import filter_final_rows

ConfidenceLevel = Literal["LOW", "MEDIUM", "HIGH"]

_EFFECT_ORDER = {"negligible": 0, "unknown": -1, "small": 1, "medium": 2, "large": 3}


def _min_total() -> int:
    try:
        return max(5, int(os.getenv("GROWTH_SEGMENT_MIN_SAMPLE", os.getenv("GROWTH_FORMAT_DECISION_MIN_SAMPLE", "50"))))
    except ValueError:
        return 50


def _min_cohort() -> int:
    try:
        return max(2, int(os.getenv("GROWTH_SEGMENT_MIN_COHORT", os.getenv("GROWTH_FORMAT_DECISION_MIN_COHORT", "20"))))
    except ValueError:
        return 20


def _alpha() -> float:
    try:
        return float(os.getenv("GROWTH_STAT_SIGNIFICANCE_ALPHA", "0.05"))
    except ValueError:
        return 0.05


def _confidence(sample_size: int, *, strategy_consistent: bool) -> ConfidenceLevel:
    if not strategy_consistent:
        return "LOW"
    if sample_size >= 250:
        return "HIGH"
    if sample_size >= 100:
        return "MEDIUM"
    return "LOW"


def _primary_effect_label(err_es: dict[str, Any], fr_es: dict[str, Any]) -> str:
    err_c = str(err_es.get("classification") or "unknown")
    fwd_c = str(fr_es.get("classification") or "unknown")
    return err_c if _EFFECT_ORDER.get(err_c, -1) <= _EFFECT_ORDER.get(fwd_c, -1) else fwd_c


def _window_rows(rows: list[dict[str, Any]], segment: str, limit: int | None) -> list[dict[str, Any]]:
    seg_rows = [r for r in rows if str(r.get("content_segment") or "") == segment]
    if limit is not None:
        seg_rows = seg_rows[:limit]
    return filter_final_rows(seg_rows)


def _metric_values(rows: list[dict[str, Any]], key: str) -> list[float]:
    return [float(r[key]) for r in rows if r.get(key) is not None]


def _recommended_mode_from_comparison(
    cmp: dict[str, Any],
    *,
    guardrails_ok: bool,
    growth_rows: list[dict[str, Any]] | None = None,
    cb_rows: list[dict[str, Any]] | None = None,
) -> tuple[str, bool, str]:
    alpha = _alpha()
    err_lift = cmp.get("err_lift_pct")
    fr_lift = cmp.get("forward_lift_pct")
    err_p = cmp.get("err_p_value")
    fr_p = cmp.get("forward_p_value")
    err_es = cmp.get("err_effect_size") or {}
    fr_es = cmp.get("forward_effect_size") or {}

    growth_wins = (
        guardrails_ok
        and err_lift is not None
        and fr_lift is not None
        and err_lift >= 10.0
        and fr_lift >= 15.0
        and err_p is not None
        and fr_p is not None
        and err_p < alpha
        and fr_p < alpha
        and effect_size_meets_minimum(str(err_es.get("classification") or ""))
        and effect_size_meets_minimum(str(fr_es.get("classification") or ""))
    )
    if growth_wins:
        return "growth_brief", True, "growth_brief_statistically_outperforms_cb"

    cb_err_p = cb_fr_p = None
    if growth_rows and cb_rows:
        cb_err_p = compare_two_samples(
            _metric_values(cb_rows, "actual_err"),
            _metric_values(growth_rows, "actual_err"),
            alternative="greater",
        ).get("p_value")
        cb_fr_p = compare_two_samples(
            _metric_values(cb_rows, "actual_forward_rate"),
            _metric_values(growth_rows, "actual_forward_rate"),
            alternative="greater",
        ).get("p_value")

    cb_wins = (
        guardrails_ok
        and err_lift is not None
        and fr_lift is not None
        and err_lift <= -10.0
        and fr_lift <= -15.0
        and cb_err_p is not None
        and cb_fr_p is not None
        and cb_err_p < alpha
        and cb_fr_p < alpha
        and effect_size_meets_minimum(str(err_es.get("classification") or ""))
        and effect_size_meets_minimum(str(fr_es.get("classification") or ""))
    )
    if cb_wins:
        return "cb_brief", True, "cb_brief_statistically_outperforms_growth"

    reason = "not_statistically_significant"
    if not guardrails_ok:
        reason = "insufficient_segment_sample"
    elif err_lift is not None and abs(err_lift) < 10.0:
        reason = "err_lift_below_threshold"
    elif fr_lift is not None and abs(fr_lift) < 15.0:
        reason = "forward_lift_below_threshold"
    return "hybrid", False, reason


def build_segment_stability(
    rows: list[dict[str, Any]],
    segment: str,
) -> dict[str, Any]:
    """Per-segment stability across last_30, last_90, all_time windows."""
    windows = {
        "last_30": _window_rows(rows, segment, 30),
        "last_90": _window_rows(rows, segment, 90),
        "all_time": _window_rows(rows, segment, None),
    }
    modes: dict[str, str] = {}
    out: dict[str, Any] = {}
    min_total = _min_total()
    min_cohort = _min_cohort()

    for name, window_rows in windows.items():
        growth_rows = [r for r in window_rows if str(r.get("format_profile") or "") == "growth_brief"]
        cb_rows = [r for r in window_rows if str(r.get("format_profile") or "") == "cb_brief"]
        guardrails_ok = (
            len(window_rows) >= min_total
            and len(growth_rows) >= min_cohort
            and len(cb_rows) >= min_cohort
        )
        if len(growth_rows) < 2 or len(cb_rows) < 2:
            out[name] = {
                "sample_size": len(window_rows),
                "recommended_mode": "hybrid",
                "statistically_significant": False,
                "err_lift_pct": None,
                "forward_lift_pct": None,
                "p_value": None,
                "effect_size": "unknown",
            }
            modes[name] = "hybrid"
            continue
        cmp = compare_content_formats(growth_rows, cb_rows)
        mode, sig, _ = _recommended_mode_from_comparison(
            cmp, guardrails_ok=guardrails_ok, growth_rows=growth_rows, cb_rows=cb_rows
        )
        err_es = cmp.get("err_effect_size") or {}
        modes[name] = mode
        out[name] = {
            "sample_size": len(window_rows),
            "recommended_mode": mode,
            "statistically_significant": sig,
            "err_lift_pct": cmp.get("err_lift_pct"),
            "forward_lift_pct": cmp.get("forward_lift_pct"),
            "p_value": cmp.get("err_p_value"),
            "effect_size": _primary_effect_label(err_es, cmp.get("forward_effect_size") or {}),
        }

    unique_modes = {m for m in modes.values() if m}
    strategy_consistent = len(unique_modes) <= 1
    return {
        "windows": out,
        "strategy_consistency": strategy_consistent,
        "recommended_modes": modes,
    }


def routing_readiness_score(
    *,
    sample_size: int,
    growth_sample: int,
    cb_sample: int,
    effect_size: str,
    strategy_consistent: bool,
    confidence: ConfidenceLevel,
    statistically_significant: bool,
) -> int:
    """0–100 readiness for future segment routing (no auto-routing in Phase 2B)."""
    cohort_n = min(growth_sample, cb_sample)
    sample_pts = min(30.0, (cohort_n / max(_min_cohort(), 1)) * 15.0 + (sample_size / max(_min_total(), 1)) * 15.0)
    effect_pts = {
        "large": 25.0,
        "medium": 18.0,
        "small": 10.0,
        "negligible": 2.0,
        "unknown": 0.0,
    }.get(effect_size, 0.0)
    stability_pts = 25.0 if strategy_consistent else 8.0
    confidence_pts = {"HIGH": 20.0, "MEDIUM": 12.0, "LOW": 5.0}.get(confidence, 5.0)
    score = sample_pts + effect_pts + stability_pts + confidence_pts
    if not statistically_significant:
        score *= 0.65
    return max(0, min(100, int(round(score))))


def evaluate_segment_strategy(
    segment: str,
    rows: list[dict[str, Any]],
    *,
    final_only: bool = True,
) -> dict[str, Any]:
    """Segment-level decision with stability and routing readiness."""
    pool = filter_final_rows(rows) if final_only else list(rows)
    seg_rows = [r for r in pool if str(r.get("content_segment") or "") == segment]
    growth_rows = [r for r in seg_rows if str(r.get("format_profile") or "") == "growth_brief"]
    cb_rows = [r for r in seg_rows if str(r.get("format_profile") or "") == "cb_brief"]

    min_total = _min_total()
    min_cohort = _min_cohort()
    guardrails_ok = (
        len(seg_rows) >= min_total
        and len(growth_rows) >= min_cohort
        and len(cb_rows) >= min_cohort
    )

    perf = _segment_performance_block(segment, growth_rows, cb_rows) if (growth_rows or cb_rows) else {
        "segment": segment,
        "growth_posts": len(growth_rows),
        "cb_posts": len(cb_rows),
        "err_lift_pct": None,
        "forward_lift_pct": None,
        "err_p_value": None,
        "forward_p_value": None,
        "p_value": None,
        "effect_size": "unknown",
    }
    cmp = perf.get("comparison") or compare_content_formats(growth_rows, cb_rows) if growth_rows and cb_rows else {}
    mode, sig, reason = _recommended_mode_from_comparison(
        cmp,
        guardrails_ok=guardrails_ok,
        growth_rows=growth_rows,
        cb_rows=cb_rows,
    ) if cmp else (
        "hybrid",
        False,
        "insufficient_segment_sample",
    )

    stability = build_segment_stability(pool, segment)
    strategy_consistent = bool(stability.get("strategy_consistency"))
    confidence = _confidence(len(seg_rows), strategy_consistent=strategy_consistent)
    if not strategy_consistent and confidence != "LOW":
        confidence = "LOW"

    readiness = routing_readiness_score(
        sample_size=len(seg_rows),
        growth_sample=len(growth_rows),
        cb_sample=len(cb_rows),
        effect_size=str(perf.get("effect_size") or "unknown"),
        strategy_consistent=strategy_consistent,
        confidence=confidence,
        statistically_significant=sig,
    )

    return {
        "segment": segment,
        "recommended_mode": mode,
        "confidence": confidence,
        "statistically_significant": sig,
        "reason": reason,
        "sample_size": len(seg_rows),
        "growth_posts": len(growth_rows),
        "cb_posts": len(cb_rows),
        "err_lift_pct": perf.get("err_lift_pct"),
        "forward_lift_pct": perf.get("forward_lift_pct"),
        "err_p_value": perf.get("err_p_value"),
        "forward_p_value": perf.get("forward_p_value"),
        "p_value": perf.get("p_value"),
        "effect_size": perf.get("effect_size"),
        "growth_err": perf.get("growth_err"),
        "cb_err": perf.get("cb_err"),
        "growth_forwards": perf.get("growth_forwards"),
        "cb_forwards": perf.get("cb_forwards"),
        "strategy_consistency": strategy_consistent,
        "stability": stability,
        "routing_readiness_score": readiness,
    }


def build_segment_decision_map(rows: list[dict[str, Any]], *, final_only: bool = True) -> dict[str, Any]:
    """Full snapshot for growth_segment_decisions.json."""
    pool = filter_final_rows(rows) if final_only else list(rows)
    segments = sorted({str(r.get("content_segment") or "general_news") for r in pool})
    decisions: dict[str, Any] = {}
    for segment in segments:
        verdict = evaluate_segment_strategy(segment, pool, final_only=False)
        decisions[segment] = {
            "recommended_mode": verdict["recommended_mode"],
            "confidence": verdict["confidence"],
            "statistically_significant": verdict["statistically_significant"],
            "routing_readiness_score": verdict["routing_readiness_score"],
            "strategy_consistency": verdict["strategy_consistency"],
            "sample_size": verdict["sample_size"],
            "err_lift_pct": verdict.get("err_lift_pct"),
            "forward_lift_pct": verdict.get("forward_lift_pct"),
            "p_value": verdict.get("p_value"),
            "effect_size": verdict.get("effect_size"),
        }
    return {"segments": decisions, "generated_from_posts": len(pool)}
