from __future__ import annotations

from bot.editorial.flow_health.doctrine.constitution import build_operational_constitution
from bot.editorial.flow_health.doctrine.doctrine_drift import detect_doctrine_drift
from bot.editorial.flow_health.doctrine.stewardship import compute_stewardship_constitution
from bot.editorial.flow_health.doctrine import doctrine_snapshot


def test_constitution_principles() -> None:
    c = build_operational_constitution()
    assert len(c["principles"]) >= 8
    assert c["doctrine_alignment_status"] in ("ALIGNED", "AT_RISK", "MISALIGNED", "DRIFTING")


def test_doctrine_drift_shape() -> None:
    const = build_operational_constitution()
    d = detect_doctrine_drift(constitution=const)
    assert "doctrine_drift_detected" in d


def test_stewardship_constitution_bands() -> None:
    s = compute_stewardship_constitution()
    assert s["stewardship_constitution_band"] in (
        "FRAGMENTED",
        "MISALIGNED",
        "ALIGNED",
        "CONSTITUTIONAL",
    )
    assert 0 <= s["stewardship_constitution_score"] <= 1


def test_doctrine_snapshot() -> None:
    snap = doctrine_snapshot()
    assert "institutional_stewardship_mode" in snap
    assert "doctrine_digest_lines" in snap
