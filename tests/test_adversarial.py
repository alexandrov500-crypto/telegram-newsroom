"""Tests for ADR-037 adversarial agent layer."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import healing_common as hc
from scripts import migration_observability_common as moc
from scripts.agents.adversarial_agent import generate_scenarios
from scripts.agents.adversarial_common import (
    ADVERSARIAL_REPORTS_DIR,
    OBSERVED_WEAKNESSES_PATH,
    append_observed_weakness,
    read_report,
)
from scripts.agents.adversarial_orchestrator import run_adversarial_pipeline
from scripts.agents.failure_injection_simulator import simulate_all
from scripts.agents.weakness_analyzer import analyze_weaknesses, summarize_weaknesses


@pytest.fixture()
def adv_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    gh = tmp_path / "github"
    gh.mkdir()
    (gh / "migration_state.txt").write_text("M0_ACTIVE\n", encoding="utf-8")
    (gh / "risk_registry.yaml").write_text(
        "risks:\n  - id: RISK-007\n    level: CRITICAL\n    status: active\n    title: dual-write\n",
        encoding="utf-8",
    )
    (gh / "incidents_store.yaml").write_text(
        "incidents:\n  - incident_id: INC-ADV-001\n"
        "    failure_reason: dual-write drift\n    severity: CRITICAL\n"
        "    phase: M0_ACTIVE\n    status: OPEN\n    impacted_issues: [P1-E04-02]\n"
        "    acknowledged: false\n    resolved: false\n    rule: test\n",
        encoding="utf-8",
    )
    (gh / "gate_evaluation_history.jsonl").write_text(
        json.dumps({"phase": "M0_ACTIVE", "gate_id": "M0_TO_M1", "status": "NO_GO", "blockers": []}) + "\n",
        encoding="utf-8",
    )
    (gh / "migration_events.jsonl").write_text("", encoding="utf-8")
    (gh / "rollback_proposals.yaml").write_text("proposals: []\n", encoding="utf-8")
    (gh / "stabilization_safety_guard.yaml").write_text("whitelist_actions: []\nhard_stops: {}\n", encoding="utf-8")
    (gh / "adversarial_observed_weaknesses.yaml").write_text("observed_weaknesses: []\n", encoding="utf-8")
    (gh / "adversarial_verifier_patterns.yaml").write_text("suggested_patterns: []\nentries: []\n", encoding="utf-8")
    (gh / "agent_decision_log.jsonl").write_text("", encoding="utf-8")
    (gh / "healing_proposals.yaml").write_text("proposals: []\n", encoding="utf-8")
    (gh / "healing_registry.yaml").write_text("patterns: []\n", encoding="utf-8")

    reports = gh / "adversarial_reports"
    reports.mkdir()

    monkeypatch.setattr(moc, "GITHUB_DIR", gh)
    monkeypatch.setattr(moc, "MIGRATION_STATE_PATH", gh / "migration_state.txt")
    monkeypatch.setattr(moc, "RISK_REGISTRY_PATH", gh / "risk_registry.yaml")
    monkeypatch.setattr(moc, "INCIDENTS_STORE_PATH", gh / "incidents_store.yaml")
    monkeypatch.setattr(moc, "GATE_HISTORY_PATH", gh / "gate_evaluation_history.jsonl")
    monkeypatch.setattr(moc, "MIGRATION_EVENTS_PATH", gh / "migration_events.jsonl")
    monkeypatch.setattr(moc, "ROLLBACK_PROPOSALS_PATH", gh / "rollback_proposals.yaml")
    monkeypatch.setattr(hc, "GITHUB_DIR", gh)

    import scripts.agents.adversarial_common as ac
    import scripts.agents.agent_core as agent_core
    import scripts.stabilization_common as sc

    monkeypatch.setattr(ac, "GITHUB_DIR", gh)
    monkeypatch.setattr(ac, "ADVERSARIAL_REPORTS_DIR", reports)
    monkeypatch.setattr(ac, "OBSERVED_WEAKNESSES_PATH", gh / "adversarial_observed_weaknesses.yaml")
    monkeypatch.setattr(ac, "ADVERSARIAL_LOG_PATH", gh / "adversarial_runs.jsonl")
    monkeypatch.setattr(ac, "VERIFIER_PATTERN_SUGGESTIONS_PATH", gh / "adversarial_verifier_patterns.yaml")
    monkeypatch.setattr(agent_core, "GITHUB_DIR", gh)
    monkeypatch.setattr(agent_core, "AGENT_DECISION_LOG_PATH", gh / "agent_decision_log.jsonl")
    monkeypatch.setattr(sc, "STABILIZATION_GUARD_PATH", gh / "stabilization_safety_guard.yaml")
    monkeypatch.setattr(sc, "GITHUB_DIR", gh)

    return gh


def test_generate_dual_write_scenarios() -> None:
    scenarios = generate_scenarios(failure_type="dual_write_inconsistency", remediation_plan={"steps": ["a", "b", "c"]})
    assert scenarios
    assert any(s.attack_vector == "race_during_dual_write" for s in scenarios)


def test_simulation_no_production_mutation(adv_env: Path) -> None:
    scenarios = generate_scenarios(failure_type="idempotency_failure")
    sims = simulate_all(scenarios)
    assert all(s.get("production_mutated") is False for s in sims)
    assert all(s.get("simulation_mode") == "logical_only" for s in sims)


def test_weakness_analyzer_finds_gaps() -> None:
    scenarios = generate_scenarios(failure_type="dual_write_inconsistency")
    sims = simulate_all(scenarios, remediation_plan={"steps": ["one"], "impacted_issues": ["P1-E04-02"]})
    weaknesses = analyze_weaknesses(scenarios, sims, remediation_plan={"steps": ["one"]})
    summary = summarize_weaknesses(weaknesses)
    assert summary["total_weaknesses"] >= 1


def test_orchestrator_writes_report(adv_env: Path) -> None:
    result = run_adversarial_pipeline(incident_id="INC-ADV-001", include_multi_agent=False)
    assert result.get("simulation_only") is True
    assert result.get("production_mutated") is False
    report = read_report("INC-ADV-001")
    assert report is not None
    assert report.get("weaknesses")


def test_observed_weakness_append(adv_env: Path) -> None:
    append_observed_weakness(
        {"incident_id": "INC-ADV-001", "attack_vector": "test_vector", "severity_if_real": "HIGH"}
    )
    data = (adv_env / "adversarial_observed_weaknesses.yaml").read_text()
    assert "test_vector" in data
