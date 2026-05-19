from __future__ import annotations

from bot.editorial.flow_health.minimalism.compression import compute_architectural_compression_score
from bot.editorial.flow_health.minimalism.entropy import measure_operational_entropy
from bot.editorial.flow_health.minimalism.redundancy import detect_governance_redundancy
from bot.editorial.flow_health.minimalism import minimalism_snapshot


def test_redundancy_shape() -> None:
    r = detect_governance_redundancy(governance={"rehearsal": {}, "doctrine": {}})
    assert "redundancy_signals" in r


def test_entropy_bounded() -> None:
    e = measure_operational_entropy()
    assert 0 <= e["operational_entropy_accumulation"] <= 1


def test_compression_bands() -> None:
    c = compute_architectural_compression_score()
    assert c["architectural_compression_band"] in ("BLOATED", "EXPANDED", "COMPRESSED", "MINIMALIST")
    assert 0 <= c["architectural_compression_score"] <= 1


def test_minimalism_snapshot() -> None:
    snap = minimalism_snapshot()
    assert "compression_candidates" in snap
    assert "minimalism_digest_lines" in snap
