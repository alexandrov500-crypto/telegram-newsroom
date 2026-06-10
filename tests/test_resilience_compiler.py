"""Tests for ADR-037 resilience compiler layer."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import migration_observability_common as moc
from scripts.resilience.guardrail_pr_generator import create_draft_pr
from scripts.resilience.guardrail_weakness_detector import detect_weaknesses
from scripts.resilience.resilience_common import (
    RESILIENCE_PROPOSALS_DIR,
    RESILIENCE_REGISTRY_PATH,
    proposal_dir,
)
from scripts.resilience.resilience_compiler_orchestrator import run_compiler
from scripts.resilience.resilience_proposal_generator import generate_proposals
from scripts.resilience.signal_aggregator import aggregate_signals


@pytest.fixture()
def resilience_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    gh = tmp_path / "github"
    gh.mkdir()
    reports = gh / "adversarial_reports"
    reports.mkdir()
    (reports / "INC-001.json").write_text(
        json.dumps(
            {
                "report_id": "AR-1",
                "incident_id": "INC-001",
                "weaknesses": [
                    {
                        "attack_vector": "race_during_dual_write",
                        "severity_if_real": "CRITICAL",
                        "weak_point": "data fork",
                    }
                ],
                "scenarios": [{"attack_vector": "race_during_dual_write"}],
                "summary": {"highest_severity": "CRITICAL"},
            }
        ),
        encoding="utf-8",
    )
    (gh / "incidents_store.yaml").write_text(
        "incidents:\n  - incident_id: INC-001\n    failure_reason: dual-write drift\n"
        "    resolved: false\n    rule: critical_risk_detected\n",
        encoding="utf-8",
    )
    (gh / "stabilization_metrics.yaml").write_text("totals: {}\nrates: {}\n", encoding="utf-8")
    (gh / "risk_registry.yaml").write_text(
        "risks:\n  - id: RISK-007\n    level: CRITICAL\n    status: active\n    title: dw\n",
        encoding="utf-8",
    )
    (gh / "healing_registry.yaml").write_text("patterns: []\n", encoding="utf-8")
    (gh / "adversarial_observed_weaknesses.yaml").write_text("observed_weaknesses: []\n", encoding="utf-8")
    (gh / "stabilization_safety_guard.yaml").write_text(
        "confidence_thresholds:\n  auto_stabilize_min: 0.92\nhard_stops:\n  dual_write_inconsistency_unresolved_prod: true\n",
        encoding="utf-8",
    )
    (gh / "adversarial_verifier_patterns.yaml").write_text("suggested_patterns: []\n", encoding="utf-8")
    (gh / "resilience_registry.yaml").write_text("proposal_history: []\nrecurring_weaknesses: []\n", encoding="utf-8")
    (gh / "migration_state.txt").write_text("M0_ACTIVE\n", encoding="utf-8")
    (gh / "gate_evaluation_history.jsonl").write_text(
        json.dumps({"gate_id": "M0_TO_M1", "status": "NO_GO", "phase": "M0_ACTIVE"}) + "\n",
        encoding="utf-8",
    )
    (gh / "migration_events.jsonl").write_text("", encoding="utf-8")
    (gh / "rollback_proposals.yaml").write_text("proposals: []\n", encoding="utf-8")

    import scripts.resilience.resilience_common as rc

    monkeypatch.setattr(moc, "GITHUB_DIR", gh)
    monkeypatch.setattr(moc, "INCIDENTS_STORE_PATH", gh / "incidents_store.yaml")
    monkeypatch.setattr(moc, "RISK_REGISTRY_PATH", gh / "risk_registry.yaml")
    monkeypatch.setattr(moc, "GATE_HISTORY_PATH", gh / "gate_evaluation_history.jsonl")
    monkeypatch.setattr(moc, "MIGRATION_STATE_PATH", gh / "migration_state.txt")
    monkeypatch.setattr(moc, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(rc, "GITHUB_DIR", gh)
    monkeypatch.setattr(rc, "ADVERSARIAL_REPORTS_DIR", reports)
    monkeypatch.setattr(rc, "INCIDENTS_STORE_PATH", gh / "incidents_store.yaml")
    monkeypatch.setattr(rc, "STABILIZATION_METRICS_PATH", gh / "stabilization_metrics.yaml")
    monkeypatch.setattr(rc, "RISK_REGISTRY_PATH", gh / "risk_registry.yaml")
    monkeypatch.setattr(rc, "HEALING_REGISTRY_PATH", gh / "healing_registry.yaml")
    monkeypatch.setattr(rc, "ADVERSARIAL_WEAKNESSES_PATH", gh / "adversarial_observed_weaknesses.yaml")
    monkeypatch.setattr(rc, "STABILIZATION_GUARD_PATH", gh / "stabilization_safety_guard.yaml")
    monkeypatch.setattr(rc, "VERIFIER_PATTERNS_PATH", gh / "adversarial_verifier_patterns.yaml")
    monkeypatch.setattr(rc, "RESILIENCE_REGISTRY_PATH", gh / "resilience_registry.yaml")
    monkeypatch.setattr(rc, "RESILIENCE_PROPOSALS_DIR", gh / "resilience-proposals")
    monkeypatch.setattr(rc, "RESILIENCE_RUNS_LOG", gh / "resilience_compiler_runs.jsonl")

    return gh


def test_signal_aggregator(resilience_env: Path) -> None:
    signals = aggregate_signals()
    assert signals["adversarial_report_count"] >= 1
    assert any(p["attack_vector"] == "race_during_dual_write" for p in signals["recurring_failure_patterns"])


def test_weakness_detector(resilience_env: Path) -> None:
    weaknesses = detect_weaknesses()
    assert weaknesses
    assert any(w.weakness_type == "dual_write_guard_gap" for w in weaknesses)


def test_proposal_generator(resilience_env: Path) -> None:
    proposal = generate_proposals()
    assert proposal.proposal_id.startswith("RES-")
    assert proposal.guardrail_changes


def test_draft_pr_artifacts(resilience_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(moc, "PROJECT_ROOT", resilience_env.parent)
    proposal = generate_proposals()
    result = create_draft_pr(proposal, dry_run=True)
    assert result["status"] == "dry_run"
    base = proposal_dir(proposal.proposal_id)
    assert (base / "DIFF.md").is_file()
    assert (base / "proposal.json").is_file()


def test_compiler_dry_run(resilience_env: Path) -> None:
    result = run_compiler(dry_run=True, skip_pr=False)
    assert result["production_mutated"] is False
    assert result["weakness_count"] >= 1
    assert result["proposal"]["proposal_id"].startswith("RES-")
