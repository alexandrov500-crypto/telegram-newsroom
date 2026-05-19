from __future__ import annotations

from bot.editorial.flow_health.rehearsal.core_freeze import validate_core_freeze_candidate
from bot.editorial.flow_health.rehearsal.drift_boundaries import analyze_drift_boundaries
from bot.editorial.flow_health.rehearsal.profiles import infer_active_rehearsal_profile
from bot.editorial.flow_health.rehearsal.recovery_calmness import compute_recovery_calmness
from bot.editorial.flow_health.rehearsal.snapshot import rehearsal_snapshot
from bot.editorial.flow_health.rehearsal.uptime_stability import validate_uptime_stability


def test_rehearsal_profile_inference() -> None:
    p = infer_active_rehearsal_profile({"flow_governance": {"degradation": {"mode": "NORMAL"}}})
    assert p["active_profile"] in p["reference_profiles"]


def test_uptime_stability_bands() -> None:
    u = validate_uptime_stability()
    assert u["uptime_stability_health"] in ("HEALTHY", "WATCH", "DEGRADED")


def test_recovery_calmness_bounded() -> None:
    c = compute_recovery_calmness(recovery_envelope={"envelope_within_bounds": True})
    assert 0.0 <= c["recovery_calmness_score"] <= 1.0


def test_drift_boundaries_shape() -> None:
    d = analyze_drift_boundaries(baseline={"baseline_deviation": 0.1})
    assert "drift_boundary_status" in d


def test_core_freeze_candidate_shape() -> None:
    f = validate_core_freeze_candidate(ctx={"publish_funnel": {"starvation": {"detected": False}}})
    assert "core_freeze_candidate" in f


def test_rehearsal_snapshot() -> None:
    r = rehearsal_snapshot()
    assert "executive_summary_lines" in r and "rehearsal_profile" in r
