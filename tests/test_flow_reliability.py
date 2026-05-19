from __future__ import annotations

from bot.editorial.flow_health.reliability.freeze_discipline import analyze_freeze_discipline
from bot.editorial.flow_health.reliability.maturity import compute_operational_maturity_index
from bot.editorial.flow_health.reliability.recovery_envelope import validate_recovery_envelope
from bot.editorial.flow_health.reliability.runtime_fatigue import compute_runtime_fatigue
from bot.editorial.flow_health.reliability.snapshot import reliability_snapshot
from bot.editorial.flow_health.reliability.survivability import validate_survivability
from bot.editorial.flow_health.reliability.telemetry_density import measure_telemetry_density


def test_survivability_bounded() -> None:
    s = validate_survivability(telemetry_ok=True, degradation={"mode": "NORMAL"})
    assert 0.0 <= s["survivability_score"] <= 1.0


def test_maturity_bands() -> None:
    m = compute_operational_maturity_index(
        trust_index={"operator_trust_index": 0.8},
        realism={"operational_realism_index": 0.7},
        simplicity={"operational_simplicity_index": 0.75},
        survivability={"survivability_score": 0.85},
        fatigue={"runtime_fatigue_score": 0.2},
        telemetry_density={"telemetry_density_score": 0.3},
        recovery_envelope={"envelope_within_bounds": True},
        degradation={"mode": "NORMAL"},
    )
    assert m["operational_maturity_band"] in ("EARLY", "STABLE", "MATURE")


def test_freeze_discipline_status() -> None:
    f = analyze_freeze_discipline(config_pressure={"advanced_touched": 0})
    assert "freeze_discipline_status" in f


def test_recovery_envelope() -> None:
    e = validate_recovery_envelope(
        adaptive={"relaxation": {"effective_scale": 0.3, "relaxation_budget_used": 0.1, "relaxation_budget_max": 0.25}},
    )
    assert e["recovery_envelope_health"] in ("healthy", "stressed")


def test_telemetry_density() -> None:
    d = measure_telemetry_density(cockpit={"cockpit_bullets": ["a"] * 8, "active_warnings": []})
    assert d["telemetry_density_score"] > 0.5


def test_reliability_snapshot_shape() -> None:
    r = reliability_snapshot(degradation={"mode": "NORMAL"})
    assert "operational_maturity" in r and "survivability" in r


def test_runtime_fatigue_shape() -> None:
    f = compute_runtime_fatigue()
    assert "runtime_fatigue_score" in f
