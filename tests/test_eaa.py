"""Tests for EAA v2 — Editorial AI Autonomy."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.editorial.eaa.controller import evaluate_editorial_autonomy_v2
from app.editorial.eaa.decision_matrix import AutonomyMode, resolve_autonomy_decision
from app.editorial.eaa.safety_envelope import evaluate_safety_envelope


@pytest.fixture(autouse=True)
def _enable_eaa(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EDITORIAL_EAA_V2_LAYER", "true")


def _layers(publish: bool = True) -> dict:
    return {
        "final_editorial_decision": {"publish": publish},
        "ugsol": {"imri": {"score": 72}, "content_flow": {"gap_minutes": 45}},
        "eml": {"attention_value": {"cognitive_value_score": 0.72}},
    }


def test_safety_envelope_blocks_spam() -> None:
    safety = evaluate_safety_envelope("Подписывайтесь на канал прямо сейчас!")
    assert safety.passes is False


def test_safety_envelope_passes_quality() -> None:
    text = (
        "Fed held rates steady. Markets reacted with moderate volatility. "
        "Почему важно: investors reassess risk allocation for Q2."
    )
    safety = evaluate_safety_envelope(text)
    assert safety.passes is True


def test_zero_human_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EDITORIAL_ZERO_HUMAN_IN_LOOP", "true")
    from app.editorial.eaa.safety_envelope import SafetyEnvelopeResult

    safety = SafetyEnvelopeResult(passes=True, violations=(), risk_score=0.1)
    aut = resolve_autonomy_decision(
        control_tower_publish=True,
        safety=safety,
        rules_approved=True,
        ai_confidence=0.75,
        imri_score=80,
        cognitive_value=0.7,
    )
    assert aut.mode == AutonomyMode.ZERO_HUMAN
    assert aut.autonomous_publish is True


def test_autonomy_rejects_low_confidence() -> None:
    from app.editorial.eaa.safety_envelope import SafetyEnvelopeResult

    safety = SafetyEnvelopeResult(passes=True, violations=(), risk_score=0.1)
    aut = resolve_autonomy_decision(
        control_tower_publish=True,
        safety=safety,
        rules_approved=False,
        ai_confidence=0.3,
        cognitive_value=0.2,
    )
    assert aut.autonomous_publish is False


def test_evaluate_editorial_autonomy_v2() -> None:
    text = (
        "Central bank signals inflation risk. Bond yields moved higher across major markets. "
        "Почему важно: portfolio duration decisions shift for the quarter."
    )
    _, extras = evaluate_editorial_autonomy_v2(text, runtime_dir=None, layer_extras=_layers())
    assert "eaa" in extras
    assert "ai_editorial_review" in extras


def test_eaa_reject_when_autonomy_fails() -> None:
    text = "short"
    _, extras = evaluate_editorial_autonomy_v2(text, runtime_dir=None, layer_extras=_layers())
    assert extras.get("eaa_reject") is True


def test_eaa_state(tmp_path: Path) -> None:
    from app.editorial.eaa.state import eaa_snapshot, record_eaa_decision

    record_eaa_decision(str(tmp_path), mode="zero_human", autonomous_publish=True, confidence=0.8, published=True)
    snap = eaa_snapshot(str(tmp_path))
    assert snap["zero_human_today"] == 1
