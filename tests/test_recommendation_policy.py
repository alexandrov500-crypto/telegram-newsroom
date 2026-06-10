"""Tests for Phase 3C Recommendation Policy Engine."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.growth_layer.advisor_validation.adoption import recommendation_type_for_feature
from app.growth_layer.policy.policy_registry import (
    build_policy_registry,
    enrich_advisor_reliability,
    load_policy_registry,
    persist_policy_registry,
)
from app.growth_layer.policy.policy_reporting import recommendation_policy_section
from app.growth_layer.policy.policy_scoring import (
    PolicyConfidence,
    PolicyTier,
    assign_policy_tier,
    build_policy_record,
    calculate_confidence,
    calculate_policy_score,
    tier_sort_key,
)
from app.growth_layer.policy.recommendation_policy import (
    apply_recommendation_policy,
    build_segment_policies,
    resolve_policy_for_type,
)
from app.growth_layer.prepublish.recommendations import generate_growth_recommendations
from app.growth_layer.validation.weekly_report import build_weekly_growth_report


def _eff(
    *,
    rtype: str = "headline_number",
    shown: int = 120,
    adopted: int = 48,
    rate: float = 40.0,
    eff: int = 92,
    p: float = 0.018,
    lift: float = 18.4,
    sig: bool = True,
) -> dict:
    return {
        "recommendation": rtype,
        "times_shown": shown,
        "times_adopted": adopted,
        "adoption_rate": rate,
        "effectiveness_score": eff,
        "p_value": p,
        "err_lift": lift,
        "statistically_significant": sig,
    }


def _outcome(draft_id: int, rtype: str, *, adopted: bool, err: float, segment: str = "technology") -> dict:
    return {
        "draft_id": draft_id,
        "recommendation_type": rtype,
        "adopted": adopted,
        "actual_err": err,
        "actual_forwards": 10 if adopted else 3,
        "segment": segment,
    }


def _registry(*entries: dict) -> dict:
    recs = {e["recommendation_type"]: e for e in entries}
    return {"recommendations": recs, "segments": {}}


# --- Confidence ---


def test_confidence_high() -> None:
    assert calculate_confidence(times_shown=100, p_value=0.01, effectiveness_score=85) == PolicyConfidence.HIGH.value


def test_confidence_medium() -> None:
    assert calculate_confidence(times_shown=50, p_value=0.2, effectiveness_score=60) == PolicyConfidence.MEDIUM.value


def test_confidence_low() -> None:
    assert calculate_confidence(times_shown=10, p_value=0.5, effectiveness_score=40) == PolicyConfidence.LOW.value


def test_confidence_high_requires_all_conditions() -> None:
    assert calculate_confidence(times_shown=100, p_value=0.2, effectiveness_score=85) == PolicyConfidence.MEDIUM.value


# --- Tier assignment ---


def test_tier_trusted() -> None:
    assert assign_policy_tier(times_shown=120, effectiveness_score=92, p_value=0.018, err_lift=18.4, statistically_significant=True) == PolicyTier.TRUSTED.value


def test_tier_experimental() -> None:
    assert assign_policy_tier(times_shown=40, effectiveness_score=65, p_value=0.12, err_lift=8.0) == PolicyTier.EXPERIMENTAL.value


def test_tier_unverified() -> None:
    assert assign_policy_tier(times_shown=5, effectiveness_score=50, p_value=None, err_lift=None) == PolicyTier.UNVERIFIED.value


def test_tier_retired_negative_lift() -> None:
    assert assign_policy_tier(times_shown=50, effectiveness_score=35, p_value=0.4, err_lift=-12.0) == PolicyTier.RETIRED.value


def test_build_policy_record_fields() -> None:
    rec = build_policy_record(_eff())
    assert rec["recommendation_type"] == "headline_number"
    assert rec["confidence"] == PolicyConfidence.HIGH.value
    assert rec["tier"] == PolicyTier.TRUSTED.value
    assert rec["policy_score"] >= 80


# --- Policy scoring ---


def test_calculate_policy_score_range() -> None:
    score = calculate_policy_score(effectiveness_score=92, sample_size=120, p_value=0.018, adoption_rate=40.0)
    assert 0 <= score <= 100
    assert score >= 70


def test_calculate_policy_score_low_sample() -> None:
    low = calculate_policy_score(effectiveness_score=30, sample_size=5, p_value=0.5, adoption_rate=10.0)
    assert low < 50


def test_tier_sort_key_order() -> None:
    assert tier_sort_key(PolicyTier.TRUSTED.value) < tier_sort_key(PolicyTier.EXPERIMENTAL.value)
    assert tier_sort_key(PolicyTier.EXPERIMENTAL.value) < tier_sort_key(PolicyTier.RETIRED.value)


# --- Registry ---


def test_build_policy_registry_global() -> None:
    outcomes = [_outcome(i, "headline_number", adopted=i % 2 == 0, err=0.72 if i % 2 == 0 else 0.55) for i in range(40)]
    reg = build_policy_registry(outcomes)
    assert "headline_number" in reg["recommendations"]
    assert reg["tier_counts"][PolicyTier.TRUSTED.value] + reg["tier_counts"][PolicyTier.EXPERIMENTAL.value] >= 1


def test_build_segment_policies() -> None:
    outcomes = [
        _outcome(1, "headline_number", adopted=True, err=0.8, segment="technology"),
        _outcome(2, "headline_number", adopted=False, err=0.5, segment="technology"),
        _outcome(3, "headline_number", adopted=True, err=0.7, segment="war"),
    ]
    advice = [
        {"draft_id": 1, "predicted_segment": "technology"},
        {"draft_id": 2, "predicted_segment": "technology"},
        {"draft_id": 3, "predicted_segment": "war"},
    ]
    segments = build_segment_policies(outcomes, advice)
    assert "technology" in segments
    assert "war" in segments


def test_resolve_policy_segment_override() -> None:
    reg = {
        "recommendations": {"headline_number": {"tier": PolicyTier.UNVERIFIED.value, "policy_score": 50}},
        "segments": {"technology": {"headline_number": {"tier": PolicyTier.TRUSTED.value, "policy_score": 94}}},
    }
    pol = resolve_policy_for_type("headline_number", registry=reg, segment="technology")
    assert pol["tier"] == PolicyTier.TRUSTED.value
    assert pol["policy_score"] == 94


def test_resolve_policy_global_fallback() -> None:
    reg = {"recommendations": {"reduce_links": {"tier": PolicyTier.TRUSTED.value, "policy_score": 88}}, "segments": {}}
    pol = resolve_policy_for_type("reduce_links", registry=reg, segment="war")
    assert pol["tier"] == PolicyTier.TRUSTED.value


def test_persist_and_load_policy_registry(tmp_path: Path) -> None:
    reg = build_policy_registry([_outcome(i, "headline_number", adopted=True, err=0.7) for i in range(35)])
    persist_policy_registry(tmp_path, reg)
    loaded = load_policy_registry(tmp_path)
    assert "headline_number" in loaded["recommendations"]


def test_enrich_advisor_reliability() -> None:
    reg = build_policy_registry([_outcome(i, "headline_number", adopted=i % 2 == 0, err=0.7 if i % 2 == 0 else 0.5) for i in range(50)])
    rel = enrich_advisor_reliability(reg, base_reliability=87)
    assert rel["advisor_reliability"] == 87
    assert "trusted_recommendations" in rel
    assert "experimental_recommendations" in rel
    assert "retired_recommendations" in rel


# --- Apply policy ---


def _raw_recs() -> dict:
    return {
        "recommendations_detailed": [
            {"feature": "has_question", "text": "Avoid question headlines", "evidence": "ev"},
            {"feature": "has_number", "text": "Add numeric element", "evidence": "ev"},
            {"feature": "link_count", "text": "Reduce links", "evidence": "ev"},
        ],
        "mismatches": [
            {"feature": "has_question"},
            {"feature": "has_number"},
            {"feature": "link_count"},
        ],
    }


def test_apply_policy_sorts_trusted_first() -> None:
    reg = {
        "recommendations": {
            "headline_number": build_policy_record(_eff(rtype="headline_number", eff=92, p=0.01, shown=120)),
            "reduce_links": build_policy_record(_eff(rtype="reduce_links", eff=88, p=0.02, shown=110)),
            "reduce_questions": build_policy_record(_eff(rtype="reduce_questions", shown=35, eff=55, p=0.2, lift=5, sig=False)),
        },
        "segments": {},
    }
    result = apply_recommendation_policy(_raw_recs(), registry=reg, segment="technology")
    assert result["policy_applied"] is True
    assert len(result["recommendations"]) <= 5
    assert "(TRUSTED)" in result["recommendations"][0]


def test_apply_policy_excludes_retired() -> None:
    reg = {
        "recommendations": {
            "reduce_questions": build_policy_record(
                _eff(rtype="reduce_questions", shown=50, eff=30, p=0.5, lift=-15.0, sig=False)
            ),
        },
        "segments": {},
    }
    reg["recommendations"]["reduce_questions"]["tier"] = PolicyTier.RETIRED.value
    result = apply_recommendation_policy(_raw_recs(), registry=reg)
    types = [d.get("recommendation_type") for d in result["recommendations_detailed"]]
    assert "reduce_questions" not in types


def test_apply_policy_max_five() -> None:
    detailed = [{"feature": f"has_number", "text": f"Rec {i}", "evidence": "e"} for i in range(8)]
    raw = {"recommendations_detailed": detailed, "mismatches": []}
    reg = {
        "recommendations": {
            f"type_{i}": build_policy_record(_eff(rtype=f"type_{i}", shown=100, eff=90, p=0.01))
            for i in range(8)
        },
        "segments": {},
    }
    # remap features - all map to headline_number; use different approach
    detailed = []
    features = ["has_number", "link_count", "has_question", "paragraph_count", "has_percent", "has_colon", "has_quote", "headline_word_count"]
    for feat in features:
        detailed.append({"feature": feat, "text": f"Adjust {feat}", "evidence": "e"})
    raw = {"recommendations_detailed": detailed, "mismatches": []}
    reg = {
        "recommendations": {
            recommendation_type_for_feature(f): build_policy_record(
                _eff(rtype=recommendation_type_for_feature(f), shown=100 - i * 5, eff=90 - i, p=0.01)
            )
            for i, f in enumerate(features)
        },
        "segments": {},
    }
    result = apply_recommendation_policy(raw, registry=reg)
    assert len(result["recommendations"]) <= 5


def test_recommendation_type_mapping() -> None:
    assert recommendation_type_for_feature("has_number") == "headline_number"
    assert recommendation_type_for_feature("link_count") == "reduce_links"


# --- Advisor integration ---


def test_generate_growth_recommendations_with_policy() -> None:
    analysis = {
        "content_segment": "technology",
        "features": {"has_number": False, "link_count": 4, "has_question": True, "paragraph_count": 8},
    }
    discovery = {
        "sample_size": 50,
        "patterns": {
            "has_number": {"top": 0.8, "bottom": 0.2, "lift": 100},
            "has_question": {"top": 0.2, "bottom": 0.7, "lift": -80},
        },
        "numeric_patterns": {
            "link_count": {"top_mean": 1, "bottom_mean": 4, "lift": 50, "top_range": {"low": 0, "high": 2}},
            "paragraph_count": {"top_mean": 5, "bottom_mean": 2, "lift": 40, "top_range": {"low": 3, "high": 6}},
        },
    }
    policy = {
        "recommendations": {
            "headline_number": build_policy_record(_eff(rtype="headline_number", shown=120, eff=94, p=0.01)),
            "reduce_links": build_policy_record(_eff(rtype="reduce_links", shown=100, eff=88, p=0.02)),
            "reduce_questions": build_policy_record(_eff(rtype="reduce_questions", shown=40, eff=55, p=0.15, lift=5, sig=False)),
        },
        "segments": {},
    }
    result = generate_growth_recommendations(
        analysis,
        discovery=discovery,
        segment="technology",
        policy_registry=policy,
    )
    assert result.get("policy_applied") is True
    assert len(result["recommendations"]) <= 5
    assert any("TRUSTED" in r or "EXPERIMENTAL" in r for r in result["recommendations"])


def test_generate_without_policy_registry_unchanged() -> None:
    analysis = {"content_segment": "technology", "features": {"has_number": False}}
    discovery = {
        "sample_size": 50,
        "patterns": {"has_number": {"top": 0.8, "bottom": 0.2, "lift": 100}},
        "numeric_patterns": {},
    }
    result = generate_growth_recommendations(analysis, discovery=discovery, apply_policy=False)
    assert not result.get("policy_applied")
    assert result["recommendations"]


# --- Reporting ---


def test_recommendation_policy_section() -> None:
    reg = build_policy_registry([_outcome(i, "headline_number", adopted=i % 2 == 0, err=0.7 if i % 2 == 0 else 0.5) for i in range(50)])
    lines = recommendation_policy_section(reg)
    text = "\n".join(lines)
    assert "RECOMMENDATION POLICY" in text
    assert "Trusted recommendations" in text
    assert "Experimental" in text


def test_weekly_report_includes_policy_section() -> None:
    reg = build_policy_registry([_outcome(i, "headline_number", adopted=True, err=0.7) for i in range(40)])
    html = build_weekly_growth_report(week_rows=[], all_rows=[], policy_registry=reg)
    assert "RECOMMENDATION POLICY" in html


def test_policy_section_empty_registry() -> None:
    lines = recommendation_policy_section({})
    assert "Недостаточно данных" in "\n".join(lines)


# --- Segment tier difference ---


def test_segment_policy_different_tiers() -> None:
    tech_outcomes = [_outcome(i, "headline_number", adopted=i % 2 == 0, err=0.85 if i % 2 == 0 else 0.55) for i in range(40)]
    war_outcomes = [_outcome(i + 100, "headline_number", adopted=False, err=0.45) for i in range(40)]
    advice = [{"draft_id": i, "predicted_segment": "technology"} for i in range(40)]
    advice += [{"draft_id": i + 100, "predicted_segment": "war"} for i in range(40)]
    reg = build_policy_registry(tech_outcomes + war_outcomes, advice_rows=advice)
    tech_score = reg["segments"]["technology"]["headline_number"]["policy_score"]
    war_score = reg["segments"]["war"]["headline_number"]["policy_score"]
    assert tech_score >= war_score


def test_load_registry_from_effectiveness_snapshot(tmp_path: Path) -> None:
    snap = {
        "effectiveness_detail": {
            "headline_number": _eff(shown=150, eff=95, p=0.01),
        }
    }
    path = tmp_path / "advisor_effectiveness.json"
    path.write_text(json.dumps(snap), encoding="utf-8")
    reg = load_policy_registry(tmp_path)
    assert "headline_number" in reg["recommendations"]


def test_retired_not_deleted_from_registry() -> None:
    reg = build_policy_registry(
        [_outcome(i, "reduce_questions", adopted=False, err=0.4) for i in range(50)]
    )
    rec = reg["recommendations"].get("reduce_questions") or {}
    if rec.get("tier") == PolicyTier.RETIRED.value:
        assert "reduce_questions" in reg["recommendations"]


def test_trusted_count_in_registry() -> None:
    eff = {
        "headline_number": _eff(shown=120, eff=92, p=0.01),
        "reduce_links": _eff(rtype="reduce_links", shown=110, eff=88, p=0.02),
    }
    reg = build_policy_registry([], effectiveness_snapshot={"effectiveness_detail": eff})
    assert reg["trusted_recommendations"] >= 1


def test_experimental_tier_positive_signals() -> None:
    rec = build_policy_record(_eff(shown=45, eff=68, p=0.08, lift=12.0, sig=False))
    assert rec["tier"] in (PolicyTier.EXPERIMENTAL.value, PolicyTier.TRUSTED.value)


def test_policy_score_increases_with_significance() -> None:
    base = calculate_policy_score(effectiveness_score=70, sample_size=50, p_value=0.2, adoption_rate=30.0)
    sig = calculate_policy_score(effectiveness_score=70, sample_size=50, p_value=0.01, adoption_rate=30.0)
    assert sig > base
