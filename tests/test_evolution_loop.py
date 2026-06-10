"""Tests for ADR-037 controlled self-evolution loop."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import migration_observability_common as moc
from scripts.evolution.controlled_apply_pipeline import apply_guardrail_changes, run_controlled_apply
from scripts.evolution.evolution_common import (
    EvolutionCandidate,
    VALIDATOR_REJECTED,
)
from scripts.evolution.evolution_decision_engine import evaluate_candidate, persist_evaluation
from scripts.evolution.evolution_orchestrator import run_evolution_loop
from scripts.evolution.guardrail_change_validator import validate_candidate
from scripts.evolution.proposal_intake import collect_candidates, persist_candidate
from scripts.evolution.regression_simulator import simulate_regression


@pytest.fixture()
def evolution_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    gh = tmp_path / "github"
    gh.mkdir()
    proposals = gh / "resilience-proposals" / "RES-TEST-001"
    proposals.mkdir(parents=True)

    proposal = {
        "proposal_id": "RES-TEST-001",
        "title": "Test evolution proposal",
        "summary": "Tighten guardrails",
        "guardrail_changes": [
            {
                "target_file": "github/stabilization_safety_guard.yaml",
                "change_type": "tighten_dual_write_guard",
                "suggested_yaml": {
                    "hard_stops": {"dual_write_inconsistency_unresolved_prod": True},
                    "confidence_thresholds": {"auto_stabilize_min": 0.94},
                },
                "rationale": "Tighten dual-write stop",
            },
            {
                "target_file": "github/adversarial_verifier_patterns.yaml",
                "change_type": "expand_verifier_patterns",
                "suggested_yaml": {"suggested_patterns": ["bypass.?guard"]},
                "rationale": "Expand verifier coverage",
            },
        ],
        "linked_incidents": ["INC-001"],
        "linked_reports": ["AR-1"],
    }
    (proposals / "proposal.json").write_text(json.dumps(proposal), encoding="utf-8")

    reports = gh / "adversarial_reports"
    reports.mkdir()
    (reports / "INC-001.json").write_text(
        json.dumps(
            {
                "report_id": "AR-1",
                "incident_id": "INC-001",
                "weaknesses": [{"attack_vector": "race_during_dual_write", "severity_if_real": "CRITICAL"}],
                "summary": {"highest_severity": "CRITICAL"},
            }
        ),
        encoding="utf-8",
    )

    (gh / "incidents_store.yaml").write_text(
        "incidents:\n  - incident_id: INC-001\n    resolved: false\n    rule: critical_risk_detected\n",
        encoding="utf-8",
    )
    (gh / "stabilization_metrics.yaml").write_text(
        "totals:\n  auto_actions_executed: 0\n  blocked_by_guard: 5\nrates: {}\n",
        encoding="utf-8",
    )
    (gh / "risk_registry.yaml").write_text(
        "risks:\n  - id: RISK-007\n    level: CRITICAL\n    status: active\n",
        encoding="utf-8",
    )
    (gh / "stabilization_safety_guard.yaml").write_text(
        "hard_stops:\n  critical_risk_active: true\n  dual_write_inconsistency_unresolved_prod: true\n"
        "confidence_thresholds:\n  auto_stabilize_min: 0.92\n",
        encoding="utf-8",
    )
    (gh / "adversarial_verifier_patterns.yaml").write_text("suggested_patterns: []\n", encoding="utf-8")
    (gh / "evolution_registry.yaml").write_text("pending_proposals: []\napplied_changes: []\n", encoding="utf-8")
    (gh / "migration_state.txt").write_text("M0_ACTIVE\n", encoding="utf-8")
    (gh / "gate_evaluation_history.jsonl").write_text(
        json.dumps({"gate_id": "M0_TO_M1", "status": "NO_GO", "phase": "M0_ACTIVE"}) + "\n",
        encoding="utf-8",
    )

    import scripts.evolution.evolution_common as ec
    import scripts.evolution.guardrail_change_validator as gcv
    import scripts.evolution.proposal_intake as pi
    import scripts.resilience.resilience_common as rc

    monkeypatch.setattr(moc, "GITHUB_DIR", gh)
    monkeypatch.setattr(moc, "INCIDENTS_STORE_PATH", gh / "incidents_store.yaml")
    monkeypatch.setattr(moc, "RISK_REGISTRY_PATH", gh / "risk_registry.yaml")
    monkeypatch.setattr(moc, "GATE_HISTORY_PATH", gh / "gate_evaluation_history.jsonl")
    monkeypatch.setattr(moc, "MIGRATION_STATE_PATH", gh / "migration_state.txt")
    monkeypatch.setattr(moc, "PROJECT_ROOT", tmp_path)

    for mod in (ec, rc):
        monkeypatch.setattr(mod, "GITHUB_DIR", gh)
    monkeypatch.setattr(ec, "EVOLUTION_REGISTRY_PATH", gh / "evolution_registry.yaml")
    monkeypatch.setattr(ec, "EVOLUTION_ARTIFACTS_DIR", gh / "evolution-artifacts")
    monkeypatch.setattr(ec, "EVOLUTION_RUNS_LOG", gh / "evolution_runs.jsonl")
    monkeypatch.setattr(ec, "STABILIZATION_GUARD_PATH", gh / "stabilization_safety_guard.yaml")
    monkeypatch.setattr(ec, "VERIFIER_PATTERNS_PATH", gh / "adversarial_verifier_patterns.yaml")
    monkeypatch.setattr(ec, "STABILIZATION_METRICS_PATH", gh / "stabilization_metrics.yaml")
    monkeypatch.setattr(ec, "ADVERSARIAL_REPORTS_DIR", reports)
    monkeypatch.setattr(ec, "RESILIENCE_PROPOSALS_DIR", gh / "resilience-proposals")
    monkeypatch.setattr(rc, "RESILIENCE_PROPOSALS_DIR", gh / "resilience-proposals")
    monkeypatch.setattr(rc, "ADVERSARIAL_REPORTS_DIR", reports)
    monkeypatch.setattr(pi, "STABILIZATION_METRICS_PATH", gh / "stabilization_metrics.yaml")
    monkeypatch.setattr(pi, "RESILIENCE_PROPOSALS_DIR", gh / "resilience-proposals")
    monkeypatch.setattr(pi, "ADVERSARIAL_REPORTS_DIR", reports)

    return gh


def test_proposal_intake(evolution_env: Path) -> None:
    candidates = collect_candidates(proposal_id="RES-TEST-001")
    assert candidates
    assert candidates[0].source_id == "RES-TEST-001"
    assert candidates[0].classification in {
        "guardrail_tweak",
        "threshold_adjustment",
        "verifier_rule_update",
    }


def test_regression_simulator_pass(evolution_env: Path) -> None:
    candidate = collect_candidates(proposal_id="RES-TEST-001")[0]
    result = simulate_regression(candidate)
    assert result.regression_passed is True
    assert result.risk_delta in {"LOW", "MED", "HIGH"}


def test_validator_rejects_weakening(evolution_env: Path) -> None:
    candidate = EvolutionCandidate(
        candidate_id="EVO-BAD",
        source_type="test",
        source_id="BAD-1",
        title="bad",
        summary="bad",
        classification="guardrail_tweak",
        guardrail_changes=[
            {
                "target_file": "github/stabilization_safety_guard.yaml",
                "change_type": "relax_dual_write_guard",
                "suggested_yaml": {
                    "hard_stops": {"dual_write_inconsistency_unresolved_prod": False},
                    "confidence_thresholds": {"auto_stabilize_min": 0.5},
                },
            }
        ],
    )
    result = validate_candidate(candidate)
    assert result.status == VALIDATOR_REJECTED
    assert result.violations


def test_decision_engine_matrix(evolution_env: Path) -> None:
    candidate = collect_candidates(proposal_id="RES-TEST-001")[0]
    payload = evaluate_candidate(candidate)
    assert payload["decision"]["action"] in {"DRAFT_PR", "HUMAN_REVIEW", "BLOCK"}
    assert payload["regression"]["regression_passed"] is True


def test_controlled_apply_blocked_without_gates(evolution_env: Path) -> None:
    candidate = collect_candidates(proposal_id="RES-TEST-001")[0]
    persist_candidate(candidate)
    payload = evaluate_candidate(candidate)
    persist_evaluation(candidate.candidate_id, payload)

    result = run_controlled_apply(candidate.candidate_id, dry_run=False)
    assert result["status"] == "blocked"
    assert result["production_mutated"] is False


def test_controlled_apply_dry_run_with_artifacts(evolution_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    candidate = collect_candidates(proposal_id="RES-TEST-001")[0]
    persist_candidate(candidate)
    payload = evaluate_candidate(candidate)
    persist_evaluation(candidate.candidate_id, payload)

    monkeypatch.setenv("EVOLUTION_APPLY_AUTHORIZED", "1")
    monkeypatch.setenv("EVOLUTION_PR_MERGED", "1")
    monkeypatch.setenv("EVOLUTION_PR_HAS_LABEL", "1")

    result = apply_guardrail_changes(
        candidate,
        dry_run=True,
        pr_merged=True,
        pr_has_label=True,
    )
    assert result["status"] == "dry_run"
    assert result["production_mutated"] is False
    assert result["applied_files"]


def test_orchestrator_dry_run(evolution_env: Path) -> None:
    result = run_evolution_loop(proposal_id="RES-TEST-001", dry_run=True)
    assert result["candidates"] >= 1
    assert result["production_mutated"] is False
    assert (evolution_env / "evolution-artifacts").is_dir()
