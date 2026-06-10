"""Tests for ADR-037 closed-loop reliability governance."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import migration_observability_common as moc
from scripts.governance.governance_common import GOVERNANCE_MEMORY_PATH, RELIABILITY_REPORTS_DIR
from scripts.governance.governance_orchestrator import run_governance
from scripts.governance.policy_drift_detector import ci_gate_blocks, detect_drift
from scripts.governance.reliability_metrics_engine import compute_metrics
from scripts.governance.reliability_report_generator import generate_report, persist_report
from scripts.governance.self_tuning_suggestion_engine import generate_suggestions


@pytest.fixture()
def governance_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
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
                    {"attack_vector": "race_during_dual_write", "severity_if_real": "CRITICAL"},
                ],
                "summary": {"highest_severity": "CRITICAL"},
            }
        ),
        encoding="utf-8",
    )

    (gh / "incidents_store.yaml").write_text(
        "incidents:\n"
        "  - incident_id: INC-001\n"
        "    rule: critical_risk_detected\n"
        "    resolved: false\n"
        "    timestamp: '2026-06-01T10:00:00Z'\n"
        "  - incident_id: INC-002\n"
        "    rule: critical_risk_detected\n"
        "    resolved: false\n"
        "    timestamp: '2026-06-02T10:00:00Z'\n",
        encoding="utf-8",
    )
    (gh / "stabilization_metrics.yaml").write_text(
        "totals:\n  stabilization_attempts: 10\n  successes: 7\n  false_positives: 2\n"
        "  auto_stabilize_count: 3\nrates:\n  success_rate: 0.7\nmttr:\n"
        "  samples: [3600, 7200, 9000, 12000]\n",
        encoding="utf-8",
    )
    (gh / "stabilization_safety_guard.yaml").write_text(
        "confidence_thresholds:\n  auto_stabilize_min: 0.92\nhard_stops:\n  critical_risk_active: true\n",
        encoding="utf-8",
    )
    (gh / "adversarial_verifier_patterns.yaml").write_text("suggested_patterns: []\n", encoding="utf-8")
    (gh / "risk_registry.yaml").write_text(
        "risks:\n  - id: RISK-007\n    level: CRITICAL\n    status: active\n",
        encoding="utf-8",
    )
    (gh / "evolution_registry.yaml").write_text(
        "applied_changes: []\npending_proposals: []\nrejected_proposals: []\nstability_delta: []\n",
        encoding="utf-8",
    )
    (gh / "governance_memory.yaml").write_text(
        "policy_changes: []\nevolution_decisions: []\n"
        "stabilization_threshold_shifts: []\nverifier_rule_modifications: []\n",
        encoding="utf-8",
    )
    (gh / "gate_evaluation_history.jsonl").write_text(
        json.dumps({"gate_id": "M0_TO_M1", "status": "NO_GO"}) + "\n" * 3,
        encoding="utf-8",
    )
    (gh / "migration_state.txt").write_text("M0_ACTIVE\n", encoding="utf-8")

    import scripts.evolution.evolution_common as ec
    import scripts.governance.governance_common as gc
    import scripts.governance.policy_drift_detector as pdd
    import scripts.resilience.resilience_common as rc

    monkeypatch.setattr(moc, "GITHUB_DIR", gh)
    monkeypatch.setattr(moc, "INCIDENTS_STORE_PATH", gh / "incidents_store.yaml")
    monkeypatch.setattr(moc, "RISK_REGISTRY_PATH", gh / "risk_registry.yaml")
    monkeypatch.setattr(moc, "GATE_HISTORY_PATH", gh / "gate_evaluation_history.jsonl")
    monkeypatch.setattr(moc, "MIGRATION_STATE_PATH", gh / "migration_state.txt")
    monkeypatch.setattr(moc, "PROJECT_ROOT", tmp_path)

    for mod in (gc, ec, rc):
        monkeypatch.setattr(mod, "GITHUB_DIR", gh)
    monkeypatch.setattr(gc, "GOVERNANCE_MEMORY_PATH", gh / "governance_memory.yaml")
    monkeypatch.setattr(gc, "RELIABILITY_REPORTS_DIR", gh / "reliability_reports")
    monkeypatch.setattr(gc, "GOVERNANCE_PROPOSALS_DIR", gh / "governance-proposals")
    monkeypatch.setattr(gc, "GOVERNANCE_RUNS_LOG", gh / "governance_runs.jsonl")
    monkeypatch.setattr(gc, "EVOLUTION_REGISTRY_PATH", gh / "evolution_registry.yaml")
    monkeypatch.setattr(gc, "STABILIZATION_METRICS_PATH", gh / "stabilization_metrics.yaml")
    monkeypatch.setattr(gc, "STABILIZATION_GUARD_PATH", gh / "stabilization_safety_guard.yaml")
    monkeypatch.setattr(gc, "VERIFIER_PATTERNS_PATH", gh / "adversarial_verifier_patterns.yaml")
    monkeypatch.setattr(gc, "INCIDENTS_STORE_PATH", gh / "incidents_store.yaml")
    monkeypatch.setattr(gc, "ADVERSARIAL_REPORTS_DIR", reports)
    monkeypatch.setattr(gc, "RISK_REGISTRY_PATH", gh / "risk_registry.yaml")
    monkeypatch.setattr(ec, "EVOLUTION_REGISTRY_PATH", gh / "evolution_registry.yaml")
    monkeypatch.setattr(rc, "ADVERSARIAL_REPORTS_DIR", reports)
    monkeypatch.setattr(pdd, "GATE_HISTORY_PATH", gh / "gate_evaluation_history.jsonl")

    return gh


def test_reliability_metrics(governance_env: Path) -> None:
    metrics = compute_metrics()
    assert "system_health_score" in metrics
    assert metrics["incident_recurrence"]["total_incidents"] >= 1
    assert metrics["adversarial_detection_coverage"] <= 0.5


def test_drift_detector(governance_env: Path) -> None:
    drift = detect_drift()
    assert drift.drift_detected is True
    assert drift.severity in {"HIGH", "CRITICAL", "MED"}


def test_self_tuning_suggestions(governance_env: Path) -> None:
    suggestions = generate_suggestions()
    assert suggestions
    assert all(s.direction in {"tighten", "review_only"} for s in suggestions)


def test_reliability_report(governance_env: Path) -> None:
    report = generate_report("2026-06-03")
    assert report["system_stability_trend"] in {"improving", "stable", "degrading", "unstable"}
    assert report["auto_apply_forbidden"] is True
    path = persist_report(report)
    assert path.is_file()


def test_ci_gate_blocks_critical_drift(governance_env: Path) -> None:
    drift = detect_drift()
    metrics = compute_metrics()
    blocked, reasons = ci_gate_blocks(drift, metrics)
    assert blocked is True
    assert reasons


def test_governance_orchestrator_dry_run(governance_env: Path) -> None:
    result = run_governance(dry_run=True, skip_pr=True)
    assert result["production_mutated"] is False
    assert result["auto_apply_forbidden"] is True
    assert (governance_env / "reliability_reports").is_dir()
    assert (governance_env / "governance-proposals").is_dir()

    mem = GOVERNANCE_MEMORY_PATH.read_text(encoding="utf-8")
    assert "tuning_proposal_generated" in mem or "policy_changes" in mem
