"""Tests for Phase 3B Advisor Effectiveness & Causal Validation."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.growth_layer.advisor_validation.adoption import (
    detect_recommendation_adoption,
    recommendation_type_for_feature,
)
from app.growth_layer.advisor_validation.causal_analysis import (
    build_feedback_readiness,
    calculate_advisor_reliability,
    compare_adopted_vs_ignored,
    compare_advice_vs_no_advice,
    rank_recommendations,
)
from app.growth_layer.advisor_validation.effectiveness import evaluate_recommendation_effectiveness
from app.growth_layer.advisor_validation.reporting import (
    build_advisor_effectiveness_snapshot,
    load_advisor_effectiveness_snapshot,
    persist_advisor_effectiveness_snapshot,
)
from app.growth_layer.editorial.feature_extraction import extract_editorial_features
from app.growth_layer.validation.weekly_report import build_weekly_growth_report
from db.advisor_outcomes_repository import list_advisor_outcomes, replace_advisor_outcomes_for_draft
from db.session import close_db, init_db, session_scope


def _advice(
    *,
    features: dict,
    detailed: list[dict],
    mismatches: list[dict] | None = None,
) -> dict:
    return {
        "features": features,
        "recommendations_detailed": detailed,
        "mismatches": mismatches or [],
        "alignment": {"score": 55},
    }


def _outcome(
    draft_id: int,
    rec_type: str,
    *,
    adopted: bool,
    err: float,
    forwards: int = 5,
) -> dict:
    return {
        "draft_id": draft_id,
        "post_id": draft_id * 100,
        "recommendation_type": rec_type,
        "adopted": adopted,
        "alignment_before": 60,
        "alignment_after": 75 if adopted else 58,
        "actual_err": err,
        "actual_forwards": forwards,
        "actual_engagement": 0.5,
        "actual_virality": 0.6,
    }


def _outcome_cohort(rec_type: str = "headline_number", n: int = 40) -> list[dict]:
    rows: list[dict] = []
    for i in range(n):
        adopted = i % 2 == 0
        rows.append(
            _outcome(
                i,
                rec_type,
                adopted=adopted,
                err=0.72 if adopted else 0.55,
                forwards=12 if adopted else 4,
            )
        )
    return rows


# --- Adoption detection ---


def test_recommendation_type_for_feature() -> None:
    assert recommendation_type_for_feature("has_number") == "headline_number"
    assert recommendation_type_for_feature("link_count") == "reduce_links"


def test_adoption_detect_number_added() -> None:
    advice = _advice(
        features={"has_number": False},
        detailed=[{"feature": "has_number", "text": "Add numeric element"}],
        mismatches=[{"feature": "has_number", "current": False, "preferred": True}],
    )
    published = {"has_number": True}
    results = detect_recommendation_adoption(advice, published, draft_features={"has_number": False})
    assert len(results) == 1
    assert results[0]["adopted"] is True
    assert results[0]["recommendation_type"] == "headline_number"


def test_adoption_detect_number_not_added() -> None:
    advice = _advice(
        features={"has_number": False},
        detailed=[{"feature": "has_number", "text": "Add numeric element"}],
        mismatches=[{"feature": "has_number", "current": False, "preferred": True}],
    )
    results = detect_recommendation_adoption(advice, {"has_number": False}, draft_features={"has_number": False})
    assert results[0]["adopted"] is False


def test_adoption_detect_links_reduced() -> None:
    advice = _advice(
        features={"link_count": 4},
        detailed=[{"feature": "link_count", "text": "Reduce links"}],
        mismatches=[{"feature": "link_count", "current": 4, "preferred_range": {"low": 0, "high": 2}}],
    )
    results = detect_recommendation_adoption(advice, {"link_count": 2}, draft_features={"link_count": 4})
    assert results[0]["adopted"] is True


def test_adoption_detect_links_not_reduced() -> None:
    advice = _advice(
        features={"link_count": 4},
        detailed=[{"feature": "link_count", "text": "Reduce links"}],
        mismatches=[{"feature": "link_count", "current": 4, "preferred_range": {"low": 0, "high": 2}}],
    )
    results = detect_recommendation_adoption(advice, {"link_count": 4}, draft_features={"link_count": 4})
    assert results[0]["adopted"] is False


def test_adoption_avoid_question_removed() -> None:
    advice = _advice(
        features={"has_question": True},
        detailed=[{"feature": "has_question", "text": "Avoid question headlines"}],
        mismatches=[{"feature": "has_question", "current": True, "preferred": False}],
    )
    results = detect_recommendation_adoption(advice, {"has_question": False}, draft_features={"has_question": True})
    assert results[0]["adopted"] is True
    assert results[0]["recommendation_type"] == "reduce_questions"


def test_adoption_empty_without_detailed() -> None:
    assert detect_recommendation_adoption({"features": {}}, {}) == []


def test_adoption_from_published_post_content() -> None:
    advice = _advice(
        features={"has_number": False},
        detailed=[{"feature": "has_number", "text": "Add numbers"}],
        mismatches=[{"feature": "has_number", "current": False, "preferred": True}],
    )
    published = extract_editorial_features({"editor_title": "5 AI trends reshape markets", "content": "", "sources": "[]"})
    results = detect_recommendation_adoption(advice, published, draft_features={"has_number": False})
    assert results[0]["adopted"] is True


def test_adoption_paragraph_count_improved() -> None:
    advice = _advice(
        features={"paragraph_count": 8},
        detailed=[{"feature": "paragraph_count", "text": "Use fewer paragraphs"}],
        mismatches=[{"feature": "paragraph_count", "current": 8, "preferred_range": {"low": 3, "high": 6}}],
    )
    results = detect_recommendation_adoption(advice, {"paragraph_count": 5}, draft_features={"paragraph_count": 8})
    assert results[0]["adopted"] is True


# --- Effectiveness ---


def test_evaluate_recommendation_effectiveness_metrics() -> None:
    rows = _outcome_cohort("headline_number", n=40)
    eff = evaluate_recommendation_effectiveness(rows)
    data = eff["headline_number"]
    assert data["times_shown"] == 40
    assert data["times_adopted"] == 20
    assert data["adoption_rate"] == 50.0
    assert data["err_lift"] is not None and data["err_lift"] > 0
    assert data["effectiveness_score"] > 0


def test_evaluate_effectiveness_skips_rows_without_actuals() -> None:
    rows = [_outcome(1, "headline_number", adopted=True, err=0.7)]
    rows[0]["actual_err"] = None
    assert evaluate_recommendation_effectiveness(rows) == {}


def test_evaluate_effectiveness_multiple_types() -> None:
    rows = _outcome_cohort("headline_number", 20) + _outcome_cohort("reduce_links", 20)
    eff = evaluate_recommendation_effectiveness(rows)
    assert "headline_number" in eff
    assert "reduce_links" in eff


def test_effectiveness_includes_p_value() -> None:
    rows = _outcome_cohort(n=50)
    eff = evaluate_recommendation_effectiveness(rows)["headline_number"]
    assert "p_value" in eff
    assert eff.get("adopted_err_avg") is not None
    assert eff.get("ignored_err_avg") is not None


# --- Causal analysis ---


def test_compare_adopted_vs_ignored() -> None:
    rows = _outcome_cohort(n=30)
    cmp = compare_adopted_vs_ignored(rows, recommendation_type="headline_number")
    assert cmp["adopted_n"] == 15
    assert cmp["ignored_n"] == 15
    assert cmp["adopted_avg"] > cmp["ignored_avg"]
    assert cmp["lift_pct"] is not None


def test_compare_advice_vs_no_advice() -> None:
    validation = [{"draft_id": i, "actual_err": 0.7 if i < 5 else 0.5} for i in range(10)]
    advice_ids = {0, 1, 2, 3, 4}
    cmp = compare_advice_vs_no_advice(validation, advice_draft_ids=advice_ids)
    assert cmp["with_advice_n"] == 5
    assert cmp["without_advice_n"] == 5
    assert cmp["with_advice_avg"] > cmp["without_advice_avg"]


def test_rank_recommendations_order() -> None:
    eff = {
        "reduce_links": {"effectiveness_score": 73, "times_shown": 50},
        "headline_number": {"effectiveness_score": 92, "times_shown": 80},
        "reduce_questions": {"effectiveness_score": 41, "times_shown": 30},
    }
    ranked = rank_recommendations(eff)
    keys = list(ranked.keys())
    assert keys[0] == "headline_number"


def test_calculate_advisor_reliability() -> None:
    eff = evaluate_recommendation_effectiveness(_outcome_cohort(n=40))
    rel = calculate_advisor_reliability(eff)
    assert 0 <= rel["advisor_reliability"] <= 100
    assert rel["tier"] in ("weak", "moderate", "good", "strong")
    assert rel["recommendations_validated"] >= 40


def test_calculate_reliability_empty() -> None:
    rel = calculate_advisor_reliability({})
    assert rel["advisor_reliability"] == 0
    assert rel["tier"] == "weak"


def test_build_feedback_readiness_no_auto_suppress() -> None:
    eff = evaluate_recommendation_effectiveness(_outcome_cohort(n=30))
    readiness = build_feedback_readiness(eff)
    for data in readiness.values():
        assert data["auto_suppress"] is False
        assert "future_weight" in data


def test_feedback_readiness_lowers_weight_without_significance() -> None:
    eff = {
        "headline_number": {
            "times_shown": 20,
            "statistically_significant": False,
            "err_lift": 5,
        }
    }
    readiness = build_feedback_readiness(eff)
    assert readiness["headline_number"]["future_weight"] < 1.0


# --- Reporting & snapshot ---


def test_build_advisor_effectiveness_snapshot() -> None:
    rows = _outcome_cohort(n=40)
    validation = [{"draft_id": i, "actual_err": 0.6} for i in range(40)]
    advice_ids = set(range(40))
    snap = build_advisor_effectiveness_snapshot(rows, validation_rows=validation, advice_draft_ids=advice_ids)
    assert snap["advisor_reliability"] is not None
    assert snap["recommendations_shown"] == 40
    assert snap["top_recommendation"] == "headline_number"
    assert "feedback_readiness" in snap


def test_persist_and_load_snapshot(tmp_path: Path) -> None:
    snap = build_advisor_effectiveness_snapshot(_outcome_cohort(n=20))
    persist_advisor_effectiveness_snapshot(tmp_path, snap)
    loaded = load_advisor_effectiveness_snapshot(tmp_path)
    assert loaded["advisor_reliability"] == snap["advisor_reliability"]


def test_weekly_report_advisor_effectiveness_section() -> None:
    snap = build_advisor_effectiveness_snapshot(_outcome_cohort(n=30))
    html = build_weekly_growth_report(
        week_rows=[],
        all_rows=[],
        advisor_snapshot=snap,
    )
    assert "ADVISOR EFFECTIVENESS" in html
    assert "Adoption rate" in html
    assert "Advisor reliability" in html


def test_weekly_report_advisor_insufficient_data() -> None:
    html = build_weekly_growth_report(week_rows=[], all_rows=[], advisor_snapshot={"recommendations_shown": 1})
    assert "ADVISOR EFFECTIVENESS" in html
    assert "Недостаточно данных" in html


# --- Persistence ---


@pytest.fixture
def sqlite_url(tmp_path: Path) -> str:
    return f"sqlite+aiosqlite:///{tmp_path / 'advisor_eff.db'}"


def test_replace_advisor_outcomes(sqlite_url: str) -> None:
    async def _run() -> None:
        await init_db(sqlite_url)
        async with session_scope() as session:
            from db.models import Draft
            from db.repository import utcnow

            draft = Draft(content="t", content_hash="ae1", sources="[]", created_at=utcnow())
            session.add(draft)
            await session.flush()
            outcomes = [
                _outcome(int(draft.id), "headline_number", adopted=True, err=0.71),
                _outcome(int(draft.id), "reduce_links", adopted=False, err=0.58),
            ]
            for o in outcomes:
                o["post_id"] = 999
            await replace_advisor_outcomes_for_draft(session, draft_id=int(draft.id), outcomes=outcomes)
            stored = await list_advisor_outcomes(session, draft_ids=[int(draft.id)])
            assert len(stored) == 2
            assert sum(1 for s in stored if s["adopted"]) == 1
        await close_db()

    asyncio.run(_run())


def test_outcomes_replace_is_idempotent(sqlite_url: str) -> None:
    async def _run() -> None:
        await init_db(sqlite_url)
        async with session_scope() as session:
            from db.models import Draft
            from db.repository import utcnow

            draft = Draft(content="t", content_hash="ae2", sources="[]", created_at=utcnow())
            session.add(draft)
            await session.flush()
            o = [_outcome(int(draft.id), "headline_number", adopted=True, err=0.8)]
            o[0]["post_id"] = 1
            await replace_advisor_outcomes_for_draft(session, draft_id=int(draft.id), outcomes=o)
            await replace_advisor_outcomes_for_draft(session, draft_id=int(draft.id), outcomes=o)
            stored = await list_advisor_outcomes(session, draft_ids=[int(draft.id)])
            assert len(stored) == 1
        await close_db()

    asyncio.run(_run())


# --- Integration-style ---


def test_full_pipeline_adoption_to_effectiveness() -> None:
    advice = _advice(
        features={"has_number": False, "link_count": 4},
        detailed=[
            {"feature": "has_number", "text": "Add numbers"},
            {"feature": "link_count", "text": "Reduce links"},
        ],
        mismatches=[
            {"feature": "has_number", "current": False, "preferred": True},
            {"feature": "link_count", "current": 4, "preferred_range": {"low": 0, "high": 2}},
        ],
    )
    published = {"has_number": True, "link_count": 2}
    adoptions = detect_recommendation_adoption(advice, published, draft_features=advice["features"])
    outcomes: list[dict] = []
    for i, a in enumerate(adoptions):
        outcomes.append(
            {
                "draft_id": i,
                "recommendation_type": a["recommendation_type"],
                "adopted": a["adopted"],
                "actual_err": 0.75 if a["adopted"] else 0.5,
                "actual_forwards": 10 if a["adopted"] else 3,
            }
        )
    eff = evaluate_recommendation_effectiveness(outcomes)
    assert len(eff) >= 1


def test_compare_adopted_vs_ignored_includes_ci() -> None:
    cmp = compare_adopted_vs_ignored(_outcome_cohort(n=24))
    assert "confidence_interval" in cmp
    assert "effect_size" in cmp


def test_snapshot_recommendations_map() -> None:
    snap = build_advisor_effectiveness_snapshot(_outcome_cohort(n=25))
    recs = snap.get("recommendations") or {}
    assert "headline_number" in recs
    assert "effectiveness_score" in recs["headline_number"]


def test_effectiveness_forward_lift() -> None:
    rows = _outcome_cohort(n=30)
    eff = evaluate_recommendation_effectiveness(rows)["headline_number"]
    assert eff.get("forward_lift") is not None


def test_advice_vs_no_advice_engagement_metric() -> None:
    validation = [{"draft_id": i, "actual_engagement": 0.8 if i < 3 else 0.4} for i in range(6)]
    cmp = compare_advice_vs_no_advice(validation, advice_draft_ids={0, 1, 2}, metric="actual_engagement")
    assert cmp["metric"] == "actual_engagement"


def test_reliability_tier_strong_at_high_score() -> None:
    eff = {
        "headline_number": {
            "times_shown": 100,
            "effectiveness_score": 95,
            "statistically_significant": True,
            "err_lift": 25,
        }
    }
    rel = calculate_advisor_reliability(eff)
    assert rel["tier"] in ("good", "strong")


def test_adoption_real_headline_change() -> None:
    advice = _advice(
        features={"has_number": False},
        detailed=[{"feature": "has_number", "text": "Add numeric element"}],
        mismatches=[{"feature": "has_number", "current": False, "preferred": True}],
    )
    draft_post = {"editor_title": "AI market expands rapidly", "content": "", "sources": "[]"}
    published_post = {"editor_title": "5 AI trends reshaping markets", "content": "", "sources": "[]"}
    draft_feats = extract_editorial_features(draft_post)
    pub_feats = extract_editorial_features(published_post)
    results = detect_recommendation_adoption(advice, pub_feats, draft_features=draft_feats)
    assert results[0]["adopted"] is True
