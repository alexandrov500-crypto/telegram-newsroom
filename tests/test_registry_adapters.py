"""Tests for ADR-037 registry read adapters."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import migration_observability_common as moc
from scripts.registry_adapters.decision_trace import load_decision_trace
from scripts.registry_adapters.event_store import load_event_store
from scripts.registry_adapters.policy_memory import load_policy_memory
from scripts.registry_adapters.unified_state import load_unified_state


@pytest.fixture()
def adapter_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    gh = tmp_path / "github"
    gh.mkdir()

    (gh / "migration_state.txt").write_text("M1_ACTIVE\n", encoding="utf-8")
    (gh / "incidents_store.yaml").write_text(
        "incidents:\n  - incident_id: INC-1\n    resolved: false\n    rule: test\n",
        encoding="utf-8",
    )
    (gh / "risk_registry.yaml").write_text(
        "risks:\n  - id: RISK-1\n    level: HIGH\n    status: active\n",
        encoding="utf-8",
    )
    (gh / "governance_memory.yaml").write_text(
        "policy_changes:\n  - change_id: GOV-1\n    source: test\n"
        "evolution_decisions: []\nstabilization_threshold_shifts: []\n",
        encoding="utf-8",
    )
    (gh / "evolution_registry.yaml").write_text(
        "pending_proposals:\n  - candidate_id: EVO-1\n    action: DRAFT_PR\n"
        "applied_changes: []\nrejected_proposals: []\n",
        encoding="utf-8",
    )
    (gh / "resilience_registry.yaml").write_text(
        "proposal_history: []\nrecurring_weaknesses: []\n",
        encoding="utf-8",
    )
    (gh / "healing_registry.yaml").write_text("patterns: []\n", encoding="utf-8")
    (gh / "healing_proposals.yaml").write_text("proposals: []\n", encoding="utf-8")
    (gh / "gate_evaluation_history.jsonl").write_text(
        json.dumps({"gate_id": "M0_TO_M1", "status": "GO", "timestamp": "2026-06-01T00:00:00Z"}) + "\n",
        encoding="utf-8",
    )
    (gh / "migration_events.jsonl").write_text("", encoding="utf-8")
    (gh / "stabilization_metrics.yaml").write_text("totals: {}\n", encoding="utf-8")
    (gh / "stabilization_safety_guard.yaml").write_text("hard_stops: {}\n", encoding="utf-8")
    (gh / "agent_decision_log.jsonl").write_text(
        json.dumps({"timestamp": "2026-06-01T00:00:00Z", "final_decision": "SUGGEST_ONLY"}) + "\n",
        encoding="utf-8",
    )

    import scripts.registry_adapters.paths as paths

    monkeypatch.setattr(moc, "GITHUB_DIR", gh)
    monkeypatch.setattr(moc, "MIGRATION_STATE_PATH", gh / "migration_state.txt")
    monkeypatch.setattr(moc, "INCIDENTS_STORE_PATH", gh / "incidents_store.yaml")
    monkeypatch.setattr(moc, "RISK_REGISTRY_PATH", gh / "risk_registry.yaml")
    monkeypatch.setattr(moc, "GATE_HISTORY_PATH", gh / "gate_evaluation_history.jsonl")
    monkeypatch.setattr(moc, "MIGRATION_EVENTS_PATH", gh / "migration_events.jsonl")

    monkeypatch.setattr(paths, "GITHUB_DIR", gh)
    monkeypatch.setattr(paths, "MIGRATION_STATE_PATH", gh / "migration_state.txt")
    monkeypatch.setattr(paths, "INCIDENTS_STORE_PATH", gh / "incidents_store.yaml")
    monkeypatch.setattr(paths, "RISK_REGISTRY_PATH", gh / "risk_registry.yaml")
    monkeypatch.setattr(paths, "GATE_HISTORY_PATH", gh / "gate_evaluation_history.jsonl")
    monkeypatch.setattr(paths, "MIGRATION_EVENTS_PATH", gh / "migration_events.jsonl")
    monkeypatch.setattr(paths, "GOVERNANCE_MEMORY_PATH", gh / "governance_memory.yaml")
    monkeypatch.setattr(paths, "EVOLUTION_REGISTRY_PATH", gh / "evolution_registry.yaml")
    monkeypatch.setattr(paths, "RESILIENCE_REGISTRY_PATH", gh / "resilience_registry.yaml")
    monkeypatch.setattr(paths, "HEALING_REGISTRY_PATH", gh / "healing_registry.yaml")
    monkeypatch.setattr(paths, "HEALING_PROPOSALS_PATH", gh / "healing_proposals.yaml")
    monkeypatch.setattr(paths, "STABILIZATION_METRICS_PATH", gh / "stabilization_metrics.yaml")
    monkeypatch.setattr(paths, "STABILIZATION_GUARD_PATH", gh / "stabilization_safety_guard.yaml")
    monkeypatch.setattr(paths, "AGENT_DECISION_LOG_PATH", gh / "agent_decision_log.jsonl")
    monkeypatch.setattr(paths, "GOVERNANCE_RUNS_LOG", gh / "governance_runs.jsonl")
    monkeypatch.setattr(paths, "EVOLUTION_RUNS_LOG", gh / "evolution_runs.jsonl")
    monkeypatch.setattr(paths, "RESILIENCE_RUNS_LOG", gh / "resilience_runs.jsonl")
    monkeypatch.setattr(paths, "ADVERSARIAL_RUNS_LOG", gh / "adversarial_runs.jsonl")
    monkeypatch.setattr(paths, "ADVERSARIAL_WEAKNESSES_PATH", gh / "adversarial_observed_weaknesses.yaml")
    monkeypatch.setattr(paths, "ADVERSARIAL_REPORTS_DIR", gh / "adversarial_reports")

    return gh


def test_policy_memory_merges_sources(adapter_env: Path) -> None:
    mem = load_policy_memory()
    assert len(mem.policy_changes) == 1
    assert len(mem.evolution_pending) == 1
    assert "governance_memory.yaml" in mem.source_files[0]


def test_event_store(adapter_env: Path) -> None:
    events = load_event_store()
    assert events.phase == "M1_ACTIVE"
    assert len(events.open_incidents()) == 1
    assert events.gate_evaluations[-1]["status"] == "GO"


def test_decision_trace(adapter_env: Path) -> None:
    trace = load_decision_trace()
    assert trace.recent()[0]["_trace_source"] == "agent"


def test_unified_state_snapshot(adapter_env: Path) -> None:
    state = load_unified_state()
    snap = state.to_snapshot()
    assert snap["unified_state"] is True
    assert snap["phase"] == "M1_ACTIVE"
    assert snap["pending_evolution"] == 1
    assert state.stop_the_line() is False
