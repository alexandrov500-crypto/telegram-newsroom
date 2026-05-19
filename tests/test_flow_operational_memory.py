from __future__ import annotations

from bot.editorial.flow_health.operational_memory.patterns import (
    compute_institutional_calmness,
    detect_recurrence,
)
from bot.editorial.flow_health.operational_memory.recoveries import classify_recovery_archetype
from bot.editorial.flow_health.operational_memory.signatures import detect_operational_signatures
from bot.editorial.flow_health.operational_memory import operational_memory_snapshot


def test_signatures_deterministic() -> None:
    sigs = detect_operational_signatures(
        certification={"change_pressure": {"change_pressure_band": "ELEVATED"}},
    )
    assert isinstance(sigs, list)


def test_recovery_archetype() -> None:
    r = classify_recovery_archetype()
    assert r["historical_recovery_mode"] in (
        "CALM_RECOVERY",
        "NOISY_RECOVERY",
        "MANUAL_STABILIZATION",
        "CHRONIC_INTERVENTION",
        "OSCILLATING_TUNING",
        "NATURAL_RECOVERY",
    )


def test_institutional_calmness_bands() -> None:
    c = compute_institutional_calmness(operational_memory={"incidents": []})
    assert c["institutional_calmness_band"] in ("REACTIVE", "STABILIZING", "MATURE", "INSTITUTIONAL")
    assert 0 <= c["institutional_calmness_index"] <= 1


def test_recurrence_shape() -> None:
    r = detect_recurrence(
        active_signatures=["VOLATILE_TUNING_PERIOD"],
        operational_memory={
            "incidents": [
                {
                    "signature": "VOLATILE_TUNING_PERIOD",
                    "occurrences": 3,
                    "last_seen_days": 2,
                },
            ],
        },
    )
    assert "recurrence_detected" in r


def test_operational_memory_snapshot() -> None:
    snap = operational_memory_snapshot()
    assert "institutional_calmness_index" in snap
    assert "memory_stewardship_lines" in snap
