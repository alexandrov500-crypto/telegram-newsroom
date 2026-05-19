from __future__ import annotations

from bot.editorial.flow_health.closure.expansion import detect_expansion_pressure
from bot.editorial.flow_health.closure.saturation import compute_governance_saturation
from bot.editorial.flow_health.closure.sufficiency import assess_architectural_sufficiency
from bot.editorial.flow_health.closure import closure_snapshot


def test_sufficiency_shape() -> None:
    s = assess_architectural_sufficiency()
    assert "architectural_sufficiency" in s


def test_saturation_bands() -> None:
    sat = compute_governance_saturation()
    assert sat["governance_saturation_band"] in ("UNDERMODELED", "EVOLVING", "MATURE", "SATURATED")


def test_expansion_pressure() -> None:
    e = detect_expansion_pressure()
    assert "expansion_pressure_detected" in e


def test_closure_snapshot() -> None:
    snap = closure_snapshot()
    assert "operational_closure_candidate" in snap
    assert "closure_digest_lines" in snap
