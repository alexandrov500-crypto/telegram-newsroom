"""Tests for ADR-037 unified state contract validation."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import migration_observability_common as moc
from scripts.registry_adapters.state_contract import validate_unified_state


@pytest.fixture()
def contract_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    gh = tmp_path / "github"
    gh.mkdir()
    (gh / "migration_state.txt").write_text("M0_ACTIVE\n", encoding="utf-8")
    (gh / "incidents_store.yaml").write_text("incidents: []\n", encoding="utf-8")
    (gh / "risk_registry.yaml").write_text("risks: []\n", encoding="utf-8")
    (gh / "governance_memory.yaml").write_text("policy_changes: []\n", encoding="utf-8")
    (gh / "evolution_registry.yaml").write_text("pending_proposals: []\n", encoding="utf-8")
    (gh / "resilience_registry.yaml").write_text("proposal_history: []\n", encoding="utf-8")
    (gh / "healing_registry.yaml").write_text("patterns: []\n", encoding="utf-8")
    (gh / "healing_proposals.yaml").write_text("proposals: []\n", encoding="utf-8")
    (gh / "gate_evaluation_history.jsonl").write_text(
        json.dumps({"gate_id": "M0_TO_M1", "status": "GO", "timestamp": "2026-06-01T00:00:00Z"}) + "\n",
        encoding="utf-8",
    )
    (gh / "migration_events.jsonl").write_text("", encoding="utf-8")
    (gh / "stabilization_metrics.yaml").write_text("totals: {}\nrates: {}\n", encoding="utf-8")
    (gh / "stabilization_safety_guard.yaml").write_text("hard_stops: {}\n", encoding="utf-8")
    (gh / "adversarial_verifier_patterns.yaml").write_text(
        "suggested_patterns: ['bypass.?guard']\n", encoding="utf-8"
    )

    import scripts.registry_adapters.paths as paths

    monkeypatch.setattr(moc, "GITHUB_DIR", gh)
    monkeypatch.setattr(moc, "MIGRATION_STATE_PATH", gh / "migration_state.txt")
    monkeypatch.setattr(moc, "INCIDENTS_STORE_PATH", gh / "incidents_store.yaml")
    monkeypatch.setattr(moc, "RISK_REGISTRY_PATH", gh / "risk_registry.yaml")
    monkeypatch.setattr(moc, "GATE_HISTORY_PATH", gh / "gate_evaluation_history.jsonl")
    monkeypatch.setattr(moc, "MIGRATION_EVENTS_PATH", gh / "migration_events.jsonl")

    for attr, val in {
        "GITHUB_DIR": gh,
        "MIGRATION_STATE_PATH": gh / "migration_state.txt",
        "INCIDENTS_STORE_PATH": gh / "incidents_store.yaml",
        "RISK_REGISTRY_PATH": gh / "risk_registry.yaml",
        "GATE_HISTORY_PATH": gh / "gate_evaluation_history.jsonl",
        "MIGRATION_EVENTS_PATH": gh / "migration_events.jsonl",
        "GOVERNANCE_MEMORY_PATH": gh / "governance_memory.yaml",
        "EVOLUTION_REGISTRY_PATH": gh / "evolution_registry.yaml",
        "RESILIENCE_REGISTRY_PATH": gh / "resilience_registry.yaml",
        "HEALING_REGISTRY_PATH": gh / "healing_registry.yaml",
        "HEALING_PROPOSALS_PATH": gh / "healing_proposals.yaml",
        "STABILIZATION_METRICS_PATH": gh / "stabilization_metrics.yaml",
        "STABILIZATION_GUARD_PATH": gh / "stabilization_safety_guard.yaml",
        "VERIFIER_PATTERNS_PATH": gh / "adversarial_verifier_patterns.yaml",
        "ADVERSARIAL_WEAKNESSES_PATH": gh / "adversarial_observed_weaknesses.yaml",
        "ADVERSARIAL_REPORTS_DIR": gh / "adversarial_reports",
        "AGENT_DECISION_LOG_PATH": gh / "agent_decision_log.jsonl",
        "GOVERNANCE_RUNS_LOG": gh / "governance_runs.jsonl",
        "EVOLUTION_RUNS_LOG": gh / "evolution_runs.jsonl",
        "RESILIENCE_RUNS_LOG": gh / "resilience_runs.jsonl",
        "ADVERSARIAL_RUNS_LOG": gh / "adversarial_runs.jsonl",
    }.items():
        monkeypatch.setattr(paths, attr, val)

    return gh


def test_runtime_validation_passes(contract_env: Path) -> None:
    result = validate_unified_state(mode="runtime")
    assert result.passed is True
    assert result.snapshot["unified_state"] is True


def test_premerge_stop_the_line_warning(contract_env: Path) -> None:
    (contract_env / "risk_registry.yaml").write_text(
        "risks:\n  - id: RISK-007\n    level: CRITICAL\n    status: active\n",
        encoding="utf-8",
    )
    result = validate_unified_state(mode="premerge")
    assert result.snapshot["stop_the_line"] is True
    assert any("STOP-THE-LINE" in w for w in result.warnings)
