from __future__ import annotations

from bot.editorial.flow_health.strategic_resilience.erosion import detect_architectural_erosion
from bot.editorial.flow_health.strategic_resilience.resilience import compute_strategic_resilience_index
from bot.editorial.flow_health.strategic_resilience.stewardship import estimate_sustainability_horizon
from bot.editorial.flow_health.strategic_resilience.sustainability import assess_sustainability_dimensions
from bot.editorial.flow_health.strategic_resilience import strategic_resilience_snapshot


def test_sustainability_dimensions() -> None:
    s = assess_sustainability_dimensions()
    assert "dimensions" in s and "sustainability_aggregate" in s


def test_erosion_detection() -> None:
    e = detect_architectural_erosion(
        certification={"change_pressure": {"change_pressure_band": "DESTABILIZING"}},
    )
    assert "architectural_erosion_detected" in e


def test_resilience_bands() -> None:
    r = compute_strategic_resilience_index()
    assert r["strategic_resilience_band"] in ("FRAGILE", "TOLERANT", "RESILIENT", "LONG_HORIZON")
    assert 0 <= r["strategic_resilience_index"] <= 1


def test_sustainability_horizon() -> None:
    h = estimate_sustainability_horizon()
    assert h["sustainability_horizon_band"] in (
        "SHORT",
        "MAINTAINED",
        "LONG",
        "INSTITUTIONAL_LONG_HORIZON",
    )


def test_strategic_resilience_snapshot() -> None:
    snap = strategic_resilience_snapshot()
    assert "strategic_resilience_index" in snap
    assert "resilience_digest_lines" in snap
