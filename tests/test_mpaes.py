"""Tests for MPAES — Multi-Persona Adaptive Editorial System."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.editorial.mpaes.cognitive_segmentation import evaluate_all_segments
from app.editorial.mpaes.controller import apply_mpaes_to_decision, enrich_draft_with_mpaes, evaluate_mpaes_state
from app.editorial.mpaes.growth_acquisition import build_growth_acquisition_plan
from app.editorial.mpaes.hub_substitution_map import evaluate_hub_substitution
from app.editorial.mpaes.narrative_adapter import adapt_narrative_for_dual_audience
from app.editorial.mpaes.operations_strategy import evaluate_operational_posture
from app.editorial.mpaes.persona_registry import DemographicSegment, REFERENCE_OPERATOR_MALE
from app.editorial.mpaes.source_affinity import evaluate_source_affinity
from app.editorial.mpaes.state import mpaes_snapshot, record_mpaes_evaluation


@pytest.fixture(autouse=True)
def _enable_mpaes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EDITORIAL_MPAES_LAYER", "true")


def test_reference_operator_male_persona_weights() -> None:
    assert REFERENCE_OPERATOR_MALE.segment == DemographicSegment.REFERENCE_OPERATOR_MALE
    assert REFERENCE_OPERATOR_MALE.topic_weights["geopolitics"] >= 0.9
    assert REFERENCE_OPERATOR_MALE.topic_weights["crypto"] >= 0.75


def test_hub_substitution_cross_domain() -> None:
    text = "Fed rates and SVO front update; BTC volatility spikes in Toronto context."
    hub = evaluate_hub_substitution(text, editorial_category="macro", cluster_size=3)
    assert hub.channels_replaced_estimate >= 6
    assert hub.substitution_score >= 60


def test_dual_audience_segmentation_passes_quality_post() -> None:
    text = (
        "ЦБ сигнализирует о риске инфляции. Почему важно: решения по ставке влияют на портфель и кредиты."
    )
    seg = evaluate_all_segments(text, editorial_category="macro")
    assert seg["dual_passes"] is True
    assert seg["dual_audience_trust"] >= 0.5


def test_narrative_adapter_injects_implication() -> None:
    text = "Markets opened lower on geopolitical tension and energy supply concerns in Europe."
    adapted = adapt_narrative_for_dual_audience(text, editorial_category="geopolitics")
    assert adapted.applied is True
    assert "Почему важно" in adapted.body


def test_source_affinity_t1_sources() -> None:
    aff = evaluate_source_affinity(
        ["reuters", "bloomberg"],
        text="Fed holds rates steady",
        editorial_category="macro",
        cluster_size=2,
    )
    assert aff.tier_quality == "T1"
    assert aff.affinity_score >= 65


def test_growth_acquisition_high_substitution() -> None:
    plan = build_growth_acquisition_plan(
        "Macro cross-domain synthesis",
        editorial_category="macro",
        primary_segment=DemographicSegment.REFERENCE_OPERATOR_MALE,
        substitution_score=80,
        reference_forward_score=72,
    )
    assert plan.share_nudge is True
    assert plan.forward_hook is not None


def test_evaluate_mpaes_state(tmp_path: Path) -> None:
    body = (
        "Canada housing and rates; crypto correlation with macro.\n\n"
        "Почему важно: один сигнал вместо десяти каналов."
    )
    result = evaluate_mpaes_state(
        body,
        runtime_dir=str(tmp_path),
        editorial_category="macro",
        sources=["reuters", "coindesk"],
        cluster_size=2,
    )
    assert result["enabled"] is True
    assert "cognitive_segmentation" in result
    assert "operational_posture" in result
    assert result["dual_audience_trust"] > 0


def test_enrich_draft_with_mpaes() -> None:
    body = "OpenAI and Nvidia reshape AI capex cycle. Markets react."
    enriched, extras = enrich_draft_with_mpaes(
        body,
        runtime_dir=None,
        editorial_category="ai",
        quality_score=72,
        is_breaking=False,
        publishing_mode="core",
        sources=["bloomberg"],
        cluster_size=2,
    )
    assert "mpaes" in extras
    assert len(enriched) >= len(body)


def test_apply_mpaes_downgrades_low_trust() -> None:
    decision = {"action": "publish", "format_mode": "context", "reasoning_trace": [], "reject": False}
    mpaes = {"mpaes": {"enabled": True, "force_digest": True, "dual_audience_trust": 0.3}}
    out = apply_mpaes_to_decision(decision, mpaes, publishing_mode="core")
    assert out["action"] == "digest"
    assert out["force_digest"] is True


def test_operational_posture_structure() -> None:
    posture = evaluate_operational_posture(dual_audience_trust=0.7, hub_substitution_score=75)
    assert posture.growth_mode.startswith("aggressive_") or posture.growth_mode.startswith("growth_")
    assert posture.frequency_tactic


def test_mpaes_state_tracking(tmp_path: Path) -> None:
    record_mpaes_evaluation(
        str(tmp_path),
        dual_audience_trust=0.72,
        hub_substitution_score=78,
        vertical="macro",
        published=True,
    )
    snap = mpaes_snapshot(str(tmp_path))
    assert snap["evaluated_today"] == 1
    assert snap["published_today"] == 1
