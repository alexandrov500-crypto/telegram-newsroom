from __future__ import annotations

from bot.editorial.flow_health.convergence import convergence_snapshot
from bot.editorial.flow_health.convergence.convergence import assess_governance_converged
from bot.editorial.flow_health.convergence.digest import build_convergence_digest_lines
from bot.editorial.flow_health.convergence.recursion import detect_stewardship_recursion
from bot.editorial.flow_health.convergence.saturation import compute_stewardship_novelty_decay
from bot.editorial.flow_health.convergence.stewardship import compute_governance_finalization


def _mature_governance() -> dict:
    return {
        "observability": {
            "governance_cohesion_status": "CANONICAL",
            "observability_integrity_band": "CANONICAL",
            "observability_drift_detected": False,
            "canonical_observability_quiet": True,
        },
        "closure": {
            "operational_closure_candidate": True,
            "architectural_sufficiency": True,
            "expansion_pressure_detected": False,
        },
        "legacy": {
            "institutional_transferability_band": "INSTITUTIONALIZED",
            "succession_readiness": True,
        },
        "doctrine": {
            "institutional_stewardship_mode": True,
            "doctrine_drift_detected": False,
        },
        "minimalism": {
            "invisible_digest_mode": True,
            "operational_entropy_accumulation": 0.1,
            "entropy": {"entropy_elevated": False},
        },
        "certification": {
            "operational_confidence": {"operational_confidence_band": "CERTIFIED"},
        },
        "rehearsal": {"uptime_stability": {"uptime_stability_health": "HEALTHY"}},
    }


def test_novelty_decay_bounded() -> None:
    n = compute_stewardship_novelty_decay(governance=_mature_governance())
    assert 0 <= n["stewardship_novelty_decay"] <= 1


def test_governance_converged_heuristic() -> None:
    novelty = {"stewardship_novelty_decay": 0.8}
    c = assess_governance_converged(governance=_mature_governance(), novelty=novelty)
    assert c["governance_converged"] is True


def test_recursion_requires_multiple_signals() -> None:
    r = detect_stewardship_recursion(governance={"certification": {}})
    assert r["stewardship_recursion_detected"] is False


def test_finalization_index_band() -> None:
    fin = compute_governance_finalization(
        converged={"governance_converged": True},
        recursion={"stewardship_recursion_detected": False},
        novelty={"stewardship_novelty_decay": 0.85},
        continuity={"governance_convergence_streak_days": 20},
        governance=_mature_governance(),
    )
    assert 0 <= fin["governance_finalization_index"] <= 1
    assert fin["governance_finalization_band"] in ("FORMING", "EVOLVED", "CONVERGED", "FINALIZED")


def test_digest_recursion_single_line() -> None:
    lines = build_convergence_digest_lines(
        recursion={
            "stewardship_recursion_detected": True,
            "recursion_signals": ["overlapping_stewardship_digest_sources"],
        },
    )
    assert len(lines) == 1
    assert "recursive" in lines[0].lower() or "recursion" in lines[0].lower()


def test_digest_finalization_quiet() -> None:
    lines = build_convergence_digest_lines(
        converged={"governance_converged": True},
        recursion={"stewardship_recursion_detected": False},
        finalization={"governance_finalization_band": "FINALIZED"},
        candidate={"governance_finalization_candidate": True},
        continuity={"governance_convergence_streak_days": 20},
        finalization_quiet=True,
    )
    assert len(lines) == 1


def test_convergence_snapshot_keys() -> None:
    snap = convergence_snapshot(governance=_mature_governance())
    assert "governance_converged" in snap
    assert "stewardship_recursion_detected" in snap
    assert "governance_finalization_index" in snap
    assert "governance_finalization_candidate" in snap
    assert "governance_convergence_streak_days" in snap
