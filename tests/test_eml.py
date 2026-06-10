"""Tests for EML — Editorial Monetization Layer."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.editorial.eml.attention_value_model import compute_attention_value
from app.editorial.eml.controller import enrich_with_editorial_monetization
from app.editorial.eml.editorial_monetization_gate import evaluate_editorial_monetization_gate
from app.editorial.eml.revenue_abstraction import RevenueAbstractionMode, abstract_revenue_potential


@pytest.fixture(autouse=True)
def _enable_eml(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EDITORIAL_EML_LAYER", "true")


def test_attention_value_breaking() -> None:
    av = compute_attention_value(substitution_score=80, is_breaking=True)
    assert av.attention_units >= 1.3


def test_revenue_blocked_on_breaking() -> None:
    av = compute_attention_value(substitution_score=80)
    rev = abstract_revenue_potential(av, is_breaking=True)
    assert rev.mode == RevenueAbstractionMode.BLOCKED_EDITORIAL
    assert rev.monetization_allowed is False


def test_monetization_gate_high_value() -> None:
    av = compute_attention_value(substitution_score=85, imri_score=82, dual_audience_trust=0.7)
    rev = abstract_revenue_potential(av, mdi_score=78)
    gate = evaluate_editorial_monetization_gate(rev, cognitive_value=av.cognitive_value_score, publish_approved=True)
    assert gate.allow_monetization is True or rev.mode == RevenueAbstractionMode.ORGANIC_ONLY


def test_enrich_with_editorial_monetization() -> None:
    layers = {
        "final_editorial_decision": {"publish": True},
        "ugsol": {"imri": {"score": 75}},
        "mpaes": {"dual_audience_trust": 0.65},
        "product_os": {"channel_substitution": {"substitution_score": 70}, "virality_v2": {"forward_prediction": 55}},
        "gmcs": {"market_dominance": {"index": 72}},
        "ccd": {"experience_fit": 0.7},
    }
    _, extras = enrich_with_editorial_monetization(
        "Macro analysis with implications for investors.",
        runtime_dir=None,
        layer_extras=layers,
        editorial_category="macro",
    )
    assert "eml" in extras
    assert "editorial_monetization" in extras


def test_eml_state(tmp_path: Path) -> None:
    from app.editorial.eml.state import record_eml_evaluation

    record_eml_evaluation(str(tmp_path), cognitive_value=0.7, value_index=0.65, monetization_allowed=True, published=True)
    from app.editorial.eml.state import eml_snapshot

    assert eml_snapshot(str(tmp_path))["monetization_eligible_today"] == 1
