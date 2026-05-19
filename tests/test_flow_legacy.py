from __future__ import annotations

from bot.editorial.flow_health.legacy.dependency import assess_stewardship_dependency_risk
from bot.editorial.flow_health.legacy.legibility import compute_operational_legibility
from bot.editorial.flow_health.legacy.stewardship import assess_institutional_transferability
from bot.editorial.flow_health.legacy import legacy_snapshot


def test_dependency_risk_bands() -> None:
    d = assess_stewardship_dependency_risk()
    assert d["stewardship_dependency_risk"] in ("LOW", "MODERATE", "HIGH")


def test_legibility_bands() -> None:
    leg = compute_operational_legibility()
    assert leg["operational_legibility_band"] in ("OPAQUE", "PARTIAL", "LEGIBLE", "INSTITUTIONAL")
    assert 0 <= leg["operational_legibility_index"] <= 1


def test_transferability_band() -> None:
    t = assess_institutional_transferability(
        dependency={"stewardship_dependency_risk": "LOW"},
        legibility={"operational_legibility_band": "LEGIBLE"},
    )
    assert t["institutional_transferability_band"] in (
        "PERSON_DEPENDENT",
        "TRANSITIONAL",
        "TRANSFERABLE",
        "INSTITUTIONALIZED",
    )


def test_legacy_snapshot() -> None:
    snap = legacy_snapshot()
    assert "succession_readiness" in snap
    assert "legacy_digest_lines" in snap
