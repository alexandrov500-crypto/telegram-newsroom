from __future__ import annotations

import math
import random
from datetime import datetime, timezone

import pytest

from app.growth_layer.statistics.confidence import bootstrap_confidence_interval
from app.growth_layer.statistics.decision_metrics import (
    build_stability_analysis,
    compare_content_formats,
    evaluate_decision_reliability,
)
from app.growth_layer.statistics.effect_size import (
    calculate_effect_size,
    classify_effect_size,
    effect_size_meets_minimum,
)
from app.growth_layer.statistics.significance import compare_two_samples
from app.growth_layer.validation.acquisition_proxy import compute_acquisition_components
from app.growth_layer.validation.decision import evaluate_format_decision


def _row(
    *,
    draft_id: int,
    fmt: str,
    err: float,
    forward_rate: float,
    engagement: float = 0.4,
    forwards: int = 5,
    tier: str = "enhanced",
    predicted: int = 55,
) -> dict:
    components = compute_acquisition_components(forwards=float(forwards), err=err, engagement=engagement)
    return {
        "draft_id": draft_id,
        "format_profile": fmt,
        "predicted_virality": predicted,
        "virality_tier": tier,
        "validation_status": "FINAL",
        "snapshot_label": "t24h",
        "actual_engagement": engagement,
        "actual_forwards": forwards,
        "actual_views": max(forwards * 50, 100),
        "actual_err": err,
        "actual_forward_rate": forward_rate,
        "actual_virality_score": engagement,
        **components,
        "published_at": datetime.now(timezone.utc).isoformat(),
    }


def _synthetic_cohort(*, n_cb: int, n_growth: int, seed: int = 42) -> list[dict]:
    rng = random.Random(seed)
    rows: list[dict] = []
    for i in range(n_cb):
        err = 0.50 + rng.uniform(-0.02, 0.02)
        fr = 0.020 + rng.uniform(-0.002, 0.002)
        rows.append(
            _row(
                draft_id=i,
                fmt="cb_brief",
                err=err,
                forward_rate=fr,
                engagement=0.35 + rng.uniform(-0.03, 0.03),
                forwards=3 + i % 2,
            )
        )
    for i in range(n_growth):
        err = 0.62 + rng.uniform(-0.02, 0.02)
        fr = 0.028 + rng.uniform(-0.002, 0.002)
        rows.append(
            _row(
                draft_id=1000 + i,
                fmt="growth_brief",
                err=err,
                forward_rate=fr,
                engagement=0.52 + rng.uniform(-0.03, 0.03),
                forwards=8 + i % 3,
                tier="viral_candidate",
                predicted=80,
            )
        )
    return rows


# --- effect size ---


def test_classify_effect_size_bands() -> None:
    assert classify_effect_size(0.1) == "negligible"
    assert classify_effect_size(0.35) == "small"
    assert classify_effect_size(0.65) == "medium"
    assert classify_effect_size(1.1) == "large"


def test_calculate_effect_size_positive_difference() -> None:
    a = [1.0, 1.1, 1.2, 1.15, 1.05]
    b = [0.5, 0.55, 0.52, 0.48, 0.51]
    result = calculate_effect_size(a, b)
    assert result["value"] is not None
    assert result["value"] > 0.8
    assert result["classification"] == "large"


def test_calculate_effect_size_insufficient_sample() -> None:
    assert calculate_effect_size([1.0], [2.0])["classification"] == "unknown"


def test_effect_size_meets_minimum() -> None:
    assert effect_size_meets_minimum("small")
    assert effect_size_meets_minimum("medium")
    assert not effect_size_meets_minimum("negligible")


# --- bootstrap CI ---


def test_bootstrap_confidence_interval_contains_mean() -> None:
    values = [0.4, 0.42, 0.38, 0.41, 0.39, 0.43, 0.37, 0.44]
    ci = bootstrap_confidence_interval(values, seed=7)
    assert ci["mean"] is not None
    assert ci["ci_low"] is not None
    assert ci["ci_high"] is not None
    assert ci["ci_low"] <= ci["mean"] <= ci["ci_high"]


def test_bootstrap_empty_values() -> None:
    ci = bootstrap_confidence_interval([])
    assert ci["mean"] is None


def test_bootstrap_single_value() -> None:
    ci = bootstrap_confidence_interval([0.55])
    assert ci["mean"] == 0.55
    assert ci["ci_low"] == 0.55


# --- significance ---


def test_compare_two_samples_detects_difference() -> None:
    growth = [0.60 + i * 0.001 for i in range(25)]
    cb = [0.50 - i * 0.001 for i in range(25)]
    result = compare_two_samples(growth, cb, alternative="greater")
    assert result["p_value"] is not None
    assert result["p_value"] < 0.05
    assert result["test"] in {"ttest_ind", "mannwhitneyu"}


def test_compare_two_samples_small_sample_warning() -> None:
    result = compare_two_samples([0.6, 0.62], [0.5, 0.51])
    assert "small_sample_size" in result["warnings"]


def test_compare_two_samples_insufficient_data() -> None:
    result = compare_two_samples([0.6], [0.5, 0.51])
    assert result["p_value"] is None
    assert result["test"] == "insufficient_data"


def test_compare_two_samples_no_difference() -> None:
    a = [0.5 + (i % 3) * 0.001 for i in range(30)]
    b = [0.5 + (i % 4) * 0.001 for i in range(30)]
    result = compare_two_samples(a, b, alternative="greater")
    assert result["p_value"] is not None
    assert result["p_value"] > 0.05


# --- compare_content_formats ---


def test_compare_content_formats_structure() -> None:
    rows = _synthetic_cohort(n_cb=25, n_growth=25)
    cb = [r for r in rows if r["format_profile"] == "cb_brief"]
    growth = [r for r in rows if r["format_profile"] == "growth_brief"]
    cmp = compare_content_formats(growth, cb)
    assert cmp["growth_mean_err"] is not None
    assert cmp["cb_mean_err"] is not None
    assert cmp["err_lift_pct"] is not None
    assert cmp["forward_lift_pct"] is not None
    assert "err_p_value" in cmp
    assert "forward_p_value" in cmp
    assert cmp["err_effect_size"]["classification"] in {"small", "medium", "large"}


def test_compare_content_formats_positive_lift() -> None:
    rows = _synthetic_cohort(n_cb=30, n_growth=30)
    cb = [r for r in rows if r["format_profile"] == "cb_brief"]
    growth = [r for r in rows if r["format_profile"] == "growth_brief"]
    cmp = compare_content_formats(growth, cb)
    assert cmp["err_lift_pct"] is not None and cmp["err_lift_pct"] > 10.0
    assert cmp["forward_lift_pct"] is not None and cmp["forward_lift_pct"] > 15.0


# --- decision reliability ---


def test_evaluate_decision_reliability_significant_cohort() -> None:
    rows = _synthetic_cohort(n_cb=30, n_growth=30)
    verdict = evaluate_decision_reliability(rows)
    assert verdict.sample_size == 60
    assert verdict.err_p_value is not None
    assert verdict.forward_p_value is not None
    assert verdict.statistically_significant is True
    assert verdict.recommended_mode == "growth_brief"
    assert verdict.effect_size in {"small", "medium", "large"}


def test_evaluate_decision_reliability_blocked_without_significance(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = _synthetic_cohort(n_cb=30, n_growth=30)

    def _fake_compare(growth_posts: list, cb_posts: list) -> dict:
        base = compare_content_formats(growth_posts, cb_posts)
        base["err_lift_pct"] = 12.0
        base["forward_lift_pct"] = 18.0
        base["err_p_value"] = 0.12
        base["forward_p_value"] = 0.08
        base["err_effect_size"] = {"value": 0.35, "classification": "small"}
        base["forward_effect_size"] = {"value": 0.4, "classification": "small"}
        return base

    monkeypatch.setattr(
        "app.growth_layer.statistics.decision_metrics.compare_content_formats",
        _fake_compare,
    )
    verdict = evaluate_decision_reliability(rows, include_stability=False)
    assert verdict.statistically_significant is False
    assert verdict.recommended_mode == "hybrid"
    assert verdict.reason == "not_statistically_significant"


def test_evaluate_decision_reliability_guardrails_control_group() -> None:
    rows = _synthetic_cohort(n_cb=5, n_growth=50)
    verdict = evaluate_decision_reliability(rows)
    assert verdict.recommended_mode == "hybrid"
    assert verdict.reason == "insufficient_control_group"


def test_evaluate_decision_reliability_confidence_levels() -> None:
    rows = _synthetic_cohort(n_cb=60, n_growth=60, seed=1)
    verdict = evaluate_decision_reliability(rows)
    assert verdict.confidence == "MEDIUM"
    assert verdict.sample_size == 120


def test_evaluate_decision_reliability_high_confidence() -> None:
    rows = _synthetic_cohort(n_cb=130, n_growth=130, seed=2)
    verdict = evaluate_decision_reliability(rows)
    assert verdict.confidence == "HIGH"
    assert verdict.sample_size >= 250


def test_evaluate_format_decision_wrapper_includes_p_values() -> None:
    rows = _synthetic_cohort(n_cb=30, n_growth=30)
    verdict = evaluate_format_decision(rows)
    assert verdict.err_p_value is not None
    assert verdict.statistically_significant is True
    d = verdict.to_dict()
    assert "err_p_value" in d
    assert "stability" in d


# --- stability windows ---


def test_build_stability_analysis_windows() -> None:
    rows = _synthetic_cohort(n_cb=50, n_growth=50)
    stability = build_stability_analysis(rows)
    assert "last_30" in stability
    assert "last_90" in stability
    assert "all_time" in stability
    assert stability["all_time"]["sample_size"] == 100
    assert "err_lift_pct" in stability["all_time"]
    assert "forward_p_value" in stability["all_time"]


def test_stability_last_30_smaller_sample() -> None:
    rows = _synthetic_cohort(n_cb=20, n_growth=20)
    stability = build_stability_analysis(rows)
    assert stability["last_30"]["sample_size"] <= 40


def test_decision_snapshot_json_fields() -> None:
    rows = _synthetic_cohort(n_cb=30, n_growth=30)
    payload = evaluate_format_decision(rows).to_dict()
    required = {
        "recommended_mode",
        "confidence",
        "sample_size",
        "statistically_significant",
        "err_lift_pct",
        "forward_lift_pct",
        "err_p_value",
        "forward_p_value",
        "effect_size",
    }
    assert required.issubset(payload.keys())
    assert payload["statistically_significant"] is True
    assert payload["err_p_value"] is not None and payload["err_p_value"] < 0.05
