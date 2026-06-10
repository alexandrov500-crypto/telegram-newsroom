"""Tests for OSGCP — Operational Stability & Growth Control Plane."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.editorial.osgcp.arbitration_engine import EditorialAction, arbitrate_editorial_decision
from app.editorial.osgcp.attention_buffer import build_buffered_narrative, record_attention_cluster
from app.editorial.osgcp.config import anti_pause_gap_trigger
from app.editorial.osgcp.continuity_controller import evaluate_continuity
from app.editorial.osgcp.controller import evaluate_osgcp
from app.editorial.osgcp.simulation import SimulationScenario, run_24h_simulation, run_all_scenarios
from app.editorial.osgcp.state import osgcp_snapshot, record_osgcp_decision
from app.editorial.osgcp.state_machine import EditorialStateKind, resolve_editorial_state


@pytest.fixture(autouse=True)
def _enable_osgcp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EDITORIAL_OSGCP", "true")
    monkeypatch.setenv("EDITORIAL_PRODUCT_OS", "true")


def test_state_machine_anti_pause_on_gap() -> None:
    state = resolve_editorial_state(gravity_avg=60, gap_minutes=anti_pause_gap_trigger() + 5, anti_pause_active=True)
    assert state.current_state == EditorialStateKind.ANTI_PAUSE


def test_state_machine_signal_on_high_gravity() -> None:
    state = resolve_editorial_state(gravity_avg=85, gap_minutes=30)
    assert state.current_state == EditorialStateKind.SIGNAL


def test_arbitration_anti_pause_overrides_reject() -> None:
    dec = arbitrate_editorial_decision(
        editorial_state=EditorialStateKind.ANTI_PAUSE,
        pg_total=40,
        gravity_total=45,
        crs_total=40,
        continuity_score=0.3,
        source_independence=0.5,
        gap_minutes=95,
        peos_reject=True,
        publishing_mode="core",
    )
    assert dec.reject is False
    assert dec.stability_override is True
    assert dec.action == EditorialAction.DIGEST


def test_arbitration_priority_on_signal_state() -> None:
    dec = arbitrate_editorial_decision(
        editorial_state=EditorialStateKind.SIGNAL,
        pg_total=72,
        gravity_total=82,
        crs_total=70,
        continuity_score=0.9,
        source_independence=0.8,
        gap_minutes=40,
    )
    assert dec.action == EditorialAction.PRIORITY_BOOST


def test_continuity_fallback_chain() -> None:
    action = evaluate_continuity(
        runtime_dir=None,
        gap_minutes=70,
        pg_total=40,
        gravity_total=45,
        crs_total=40,
        can_publish=False,
    )
    assert action.triggered is True
    assert len(action.fallback_chain_used) >= 1


def test_attention_buffer_and_narrative(tmp_path: Path) -> None:
    record_attention_cluster(
        str(tmp_path),
        fingerprint="abc",
        combined_text="Fed raised rates affecting markets",
        quality_score=65,
    )
    narrative = build_buffered_narrative(str(tmp_path))
    assert narrative is not None
    assert narrative.mode.value in {"synthesis", "context_merge", "signal_replay"}


def test_evaluate_osgcp_shipping_authority(tmp_path: Path) -> None:
    layer = {
        "product_os": {"product_gravity": {"total": 78.0}},
        "editorial_dominance": {"gravity": {"total": 75.0}, "source_graph": {"independence_score": 0.8}},
        "audience_unification": {"crs": {"total": 72.0}},
    }
    _, extras = evaluate_osgcp(
        "Fed cut rates. Markets reacted. Why it matters for investors.",
        runtime_dir=str(tmp_path),
        publishing_mode="core",
        quality_score=62,
        cluster_size=2,
        cluster_texts=["Fed cut rates", "Markets reacted"],
        layer_extras=layer,
    )
    assert "osgcp" in extras
    assert extras["osgcp"]["shipping_authority"] == "osgcp_advisory"
    assert extras["osgcp"]["final_authority"] == "ugsol_control_tower"
    assert "editorial_decision" in extras["osgcp"]


def test_simulation_high_signal_day() -> None:
    report = run_24h_simulation(SimulationScenario.HIGH_SIGNAL)
    assert report.expected_posts_per_day >= 5
    assert report.gravity_avg >= 50


def test_simulation_all_scenarios() -> None:
    reports = run_all_scenarios()
    assert "high_signal_day" in reports
    assert "low_signal_day" in reports
    assert "mixed_volatility_day" in reports


def test_osgcp_state_tracking(tmp_path: Path) -> None:
    record_osgcp_decision(
        str(tmp_path),
        editorial_state="normal_state",
        action="publish",
        format_mode="context",
        continuity_triggered=False,
        published=True,
    )
    snap = osgcp_snapshot(str(tmp_path))
    assert snap["evaluated_today"] == 1
    assert snap["published_today"] == 1


def test_osgcp_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EDITORIAL_OSGCP", "false")
    out, extras = evaluate_osgcp("test", runtime_dir=None, publishing_mode="core", quality_score=50)
    assert out == "test"
    assert extras == {}
