"""Tests for UGSOL — Unified Growth & Stability Orchestration Layer."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.editorial.ugsol.audience_dominance_balancer import CorrectionAction, evaluate_audience_balance
from app.editorial.ugsol.content_flow_governor import ForcedMode, evaluate_content_flow
from app.editorial.ugsol.control_tower import resolve_final_editorial_decision
from app.editorial.ugsol.controller import run_ugsol_control_tower
from app.editorial.ugsol.feedback_reinjection import compute_feedback_adjustments
from app.editorial.ugsol.imri import IMRIMode, compute_imri
from app.editorial.ugsol.objective_function import compute_system_objective
from app.editorial.ugsol.state import record_control_tower_decision, ugsol_snapshot
from app.editorial.ugsol.system_simulator import SimulationScenario, run_all_scenarios, run_scenario


@pytest.fixture(autouse=True)
def _enable_ugsol(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EDITORIAL_UGSOL_LAYER", "true")


def _layer_stack(*, osgcp_reject: bool = False, anti_pause: bool = False) -> dict:
    return {
        "product_os": {
            "product_gravity": {"total": 72},
            "channel_substitution": {"substitution_score": 68},
            "virality_v2": {"forward_prediction": 55},
        },
        "mpaes": {
            "dual_audience_trust": 0.65,
            "primary_segment": "reference_operator_male",
            "cognitive_segmentation": {"segments": []},
            "hub_substitution": {"substitution_score": 70},
        },
        "ccd": {"experience_fit": 0.7},
        "osgcp": {
            "format_mode": "context",
            "editorial_decision": {
                "action": "reject" if osgcp_reject else "publish",
                "format_mode": "context",
                "reject": osgcp_reject,
                "stability_override": anti_pause,
            },
            "continuity": {"triggered": anti_pause},
            "anti_pause": {"anti_pause_active": anti_pause},
        },
        "osgcp_reject": osgcp_reject,
    }


def test_imri_dominance_mode() -> None:
    imri = compute_imri(
        substitution_rate=95,
        forward_rate=0.9,
        save_rate=0.8,
        return_frequency=0.9,
        cross_domain_coverage=0.9,
    )
    assert imri.score >= 80
    assert imri.mode == IMRIMode.DOMINANCE


def test_imri_recovery_mode() -> None:
    imri = compute_imri(substitution_rate=40, forward_rate=0.1, save_rate=0.05, return_frequency=0.2)
    assert imri.mode == IMRIMode.RECOVERY


def test_audience_balance_unified_core() -> None:
    bal = evaluate_audience_balance(forward_rate_male=0.5, forward_rate_female=0.48)
    assert bal.correction_action == CorrectionAction.UNIFIED_CORE
    assert abs(bal.male_weight + bal.female_weight - 1.0) < 0.01


def test_content_flow_anti_pause_forces_digest() -> None:
    flow = evaluate_content_flow(
        runtime_dir=None,
        starvation=True,
        newsroom_tz="UTC",
    )
    assert flow.allow_publish is True
    assert flow.forced_mode_override in {ForcedMode.DIGEST, ForcedMode.SYNTHESIS}


def test_control_tower_final_authority_publish() -> None:
    decision, meta = resolve_final_editorial_decision(_layer_stack())
    assert decision.publish is True
    assert "ugsol:control_tower_entry" in decision.reasoning_chain
    assert meta["final_decision"]["authority"] == "ugsol_control_tower_final"


def test_control_tower_overrides_osgcp_reject_on_continuity() -> None:
    decision, _ = resolve_final_editorial_decision(_layer_stack(osgcp_reject=True, anti_pause=True))
    assert decision.publish is True
    assert decision.mode.value in {"digest", "synthesis", "context"}


def test_control_tower_downgrades_osgcp_reject_to_digest(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.editorial.ugsol.content_flow_governor import FlowDecision, ForcedMode

    monkeypatch.setattr(
        "app.editorial.ugsol.control_tower.evaluate_content_flow",
        lambda **kw: FlowDecision(
            allow_publish=True,
            forced_mode_override=ForcedMode.NONE,
            inserted_synthesis=False,
            spacing_adjustment_minutes=0,
            gap_minutes=30.0,
            reason="test",
        ),
    )
    layers = _layer_stack(osgcp_reject=True)
    layers["product_os"]["channel_substitution"]["substitution_score"] = 72
    layers["mpaes"]["hub_substitution"]["substitution_score"] = 74
    decision, _ = resolve_final_editorial_decision(layers)
    assert decision.publish is True
    assert decision.mode.value == "digest"
    assert "ugsol:downgrade_osgcp_reject_to_digest" in decision.reasoning_chain


def test_run_ugsol_control_tower_integration() -> None:
    _, extras = run_ugsol_control_tower(
        "Fed holds rates. Почему важно: investors reassess risk.",
        runtime_dir=None,
        layer_extras=_layer_stack(),
        publishing_mode="core",
    )
    assert extras["ugsol"]["shipping_authority"] == "ugsol_control_tower"
    assert "final_editorial_decision" in extras


def test_system_objective_not_volume() -> None:
    obj = compute_system_objective(substitution_score=75, dual_audience_trust=0.7, continuity_score=0.8)
    assert obj.composite_score > 0
    assert "raw_volume" in obj.to_dict()["not_optimizing_for"][0] or "raw_volume" in str(
        obj.to_dict()["not_optimizing_for"]
    )


def test_feedback_reinjection_cognitive_signal() -> None:
    adj = compute_feedback_adjustments(forward_rate=0.7, save_rate=0.5, return_rate=0.6, imri_score=82)
    assert adj.egdl_gravity_bias >= 0


def test_system_simulator_all_scenarios() -> None:
    result = run_all_scenarios()
    assert len(result["scenarios"]) == 3
    assert "avg_substitution_efficiency" in result["summary"]


def test_simulator_high_volatility(tmp_path: Path) -> None:
    sim = run_scenario(SimulationScenario.HIGH_VOLATILITY, runtime_dir=str(tmp_path), slots=6)
    assert sim.publish_count >= 1
    assert len(sim.imri_trajectory) == 6


def test_ugsol_state_tracking(tmp_path: Path) -> None:
    record_control_tower_decision(
        str(tmp_path),
        publish=True,
        mode="context",
        priority_level="normal",
        imri_score=75,
        objective_score=0.6,
        published=True,
    )
    snap = ugsol_snapshot(str(tmp_path))
    assert snap["published_today"] == 1
