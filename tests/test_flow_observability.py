from __future__ import annotations

from bot.editorial.flow_health.observability import observability_snapshot
from bot.editorial.flow_health.observability.cohesion import assess_governance_cohesion
from bot.editorial.flow_health.observability.consistency import detect_observability_drift
from bot.editorial.flow_health.observability.continuity import is_canonical_truth_day
from bot.editorial.flow_health.observability.digest import build_observability_digest_lines
from bot.editorial.flow_health.observability.integrity import compute_observability_integrity
from bot.editorial.flow_health.observability.propagation import verify_canonical_propagation


def test_propagation_detects_stale_scalar_read() -> None:
    gov = {
        "closure": {"operational_closure_candidate": True},
        "legacy": {"succession_readiness": False},
    }
    prop = verify_canonical_propagation(
        enriched_governance=gov,
        collector_ctx={"flow_closure": gov["closure"]},
    )
    assert "stale_read_operational_closure_candidate" in prop["propagation_signals"]
    assert prop["propagation_coherent"] is False


def test_propagation_coherent_when_aligned() -> None:
    gov = {
        "closure": {"operational_closure_candidate": True},
        "minimalism": {"architectural_compression_score": 0.8},
    }
    prop = verify_canonical_propagation(
        enriched_governance=gov,
        collector_ctx={
            "operational_closure_candidate": True,
            "architectural_compression_score": 0.8,
        },
    )
    assert prop["propagation_coherent"] is True


def test_cohesion_bands() -> None:
    c = assess_governance_cohesion(
        governance={"certification": {}, "legacy": {}},
        propagation={"propagation_coherent": False, "propagation_signals": ["a", "b", "c"]},
    )
    assert c["governance_cohesion_status"] == "FRAGMENTED"


def test_integrity_index_bounded() -> None:
    integrity = compute_observability_integrity(
        cohesion={"governance_cohesion_status": "COHERENT"},
        propagation={"propagation_coherent": True},
        drift={"observability_drift_detected": False},
    )
    assert 0 <= integrity["observability_integrity_index"] <= 1
    assert integrity["observability_integrity_band"] in (
        "FRAGILE",
        "INCONSISTENT",
        "STABLE",
        "CANONICAL",
    )


def test_drift_advisory_only() -> None:
    drift = detect_observability_drift(
        governance={
            "freeze_registry": {"drift_exposure": {"drift_exposure_band": "MINIMAL"}},
            "rehearsal": {"uptime_stability": {"uptime_stability_health": "DEGRADED"}},
        },
    )
    assert drift["observability_drift_detected"] is True


def test_canonical_truth_day() -> None:
    assert is_canonical_truth_day(
        cohesion={"governance_cohesion_status": "COHERENT"},
        integrity={"observability_integrity_band": "STABLE"},
        propagation={"propagation_coherent": True},
        drift={"observability_drift_detected": False},
    )


def test_digest_quiet_single_line() -> None:
    lines = build_observability_digest_lines(
        cohesion={"governance_cohesion_status": "CANONICAL"},
        integrity={"observability_integrity_band": "CANONICAL"},
        drift={"observability_drift_detected": False},
        continuity={"canonical_truth_streak_days": 10},
        canonical_quiet=True,
    )
    assert len(lines) == 1
    assert "coherent" in lines[0].lower() or "consistent" in lines[0].lower()


def test_observability_snapshot_keys() -> None:
    snap = observability_snapshot(
        governance={"certification": {}, "closure": {}, "legacy": {}},
        collector_ctx={},
    )
    assert snap["governance_cohesion_status"] in (
        "FRAGMENTED",
        "PARTIAL",
        "COHERENT",
        "CANONICAL",
    )
    assert "observability_integrity_index" in snap
    assert "observability_drift_detected" in snap
    assert "canonical_truth_streak_days" in snap
