from __future__ import annotations

from bot.editorial.flow_health.certification.change_pressure import measure_change_pressure
from bot.editorial.flow_health.certification.confidence import compute_operational_confidence
from bot.editorial.flow_health.certification.evidence import build_operational_evidence_summary
from bot.editorial.flow_health.certification.freeze_governance import assess_stabilization_freeze
from bot.editorial.flow_health.certification.lockdown import analyze_configuration_lockdown
from bot.editorial.flow_health.certification.snapshot import certification_snapshot


def test_stabilization_freeze_shape() -> None:
    s = assess_stabilization_freeze()
    assert s["stabilization_freeze_status"] in ("STABLE_FREEZE", "FREEZE_AT_RISK", "FREEZE_VIOLATIONS")


def test_evidence_summary() -> None:
    e = build_operational_evidence_summary(ctx={"flow_cadence": {"cadence_health": 0.6}})
    assert "operational_evidence_summary" in e


def test_lockdown_candidates() -> None:
    l = analyze_configuration_lockdown()
    assert "lockdown_candidates" in l and 0 <= l["locked_surface_ratio"] <= 1


def test_change_pressure_bands() -> None:
    c = measure_change_pressure()
    assert c["change_pressure_band"] in ("LOW", "ELEVATED", "DESTABILIZING")


def test_confidence_bands() -> None:
    c = compute_operational_confidence()
    assert c["operational_confidence_band"] in ("PROVISIONAL", "TRUSTED", "CERTIFIED")


def test_certification_snapshot() -> None:
    snap = certification_snapshot()
    assert "stewardship_summary_lines" in snap
    assert "operational_certification" in snap
