from __future__ import annotations

from bot.editorial.flow_health.baseline_immunity import apply_baseline_immunity
from bot.editorial.flow_health.degradation import detect_degradation_mode, heuristic_gates
from bot.editorial.flow_health.influence import compute_active_influences
from bot.editorial.flow_health.simplicity import compute_operational_simplicity_index


def test_degradation_modes() -> None:
    d = detect_degradation_mode(
        baseline={"drift_detected": True, "baseline_deviation": 0.4},
        telemetry_ok=False,
    )
    assert d["mode"] in ("NORMAL", "SIMPLIFIED", "SAFE_BASELINE", "TELEMETRY_DEGRADED")
    assert "gates" in d


def test_heuristic_gates_normal() -> None:
    g = heuristic_gates("NORMAL")
    assert g["vitality_nudges"] is True
    assert g["advanced_calibration"] is True


def test_baseline_immunity_pass_through() -> None:
    b = apply_baseline_immunity({"baseline_deviation": 0.1, "drift_detected": False})
    assert "immunity_active" in b


def test_simplicity_bounded() -> None:
    s = compute_operational_simplicity_index(
        config_pressure={"configuration_pressure_score": 0.2},
        warning_pressure=0.1,
        influences={"influence_count": 4},
        degradation={"mode": "NORMAL"},
        baseline={"baseline_deviation": 0.1},
        freshness={"adaptive_freshness_score": 0.8},
    )
    assert 0.0 <= s["operational_simplicity_index"] <= 1.0


def test_active_influences_shape() -> None:
    inf = compute_active_influences(
        adaptive={"starvation_active": True, "relaxation": {"effective_scale": 0.2}},
    )
    assert "active_influences" in inf
