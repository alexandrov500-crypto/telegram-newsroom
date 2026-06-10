"""Tests for ADR-037 migration observability layer."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import migration_observability_common as moc


@pytest.fixture()
def obs_github(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    gh = tmp_path / "github"
    gh.mkdir()
    (gh / "migration_state.txt").write_text("M0_ACTIVE\n", encoding="utf-8")
    (gh / "risk_registry.yaml").write_text(
        "risks:\n"
        "  - id: RISK-007\n"
        "    title: Dual-write drift\n"
        "    level: CRITICAL\n"
        "    status: active\n"
        "    impacted_issues: [P1-E04-02]\n",
        encoding="utf-8",
    )
    (gh / "incidents_store.yaml").write_text("incidents: []\n", encoding="utf-8")
    (gh / "rollback_proposals.yaml").write_text("proposals: []\n", encoding="utf-8")
    (gh / "gate_evaluation_history.jsonl").write_text("", encoding="utf-8")
    (gh / "migration_events.jsonl").write_text("", encoding="utf-8")

    monkeypatch.setattr(moc, "GITHUB_DIR", gh)
    monkeypatch.setattr(moc, "MIGRATION_STATE_PATH", gh / "migration_state.txt")
    monkeypatch.setattr(moc, "GATE_SNAPSHOT_PATH", gh / "gate_status_snapshot.md")
    monkeypatch.setattr(moc, "RISK_REGISTRY_PATH", gh / "risk_registry.yaml")
    monkeypatch.setattr(moc, "INCIDENTS_STORE_PATH", gh / "incidents_store.yaml")
    monkeypatch.setattr(moc, "ROLLBACK_PROPOSALS_PATH", gh / "rollback_proposals.yaml")
    monkeypatch.setattr(moc, "GATE_HISTORY_PATH", gh / "gate_evaluation_history.jsonl")
    monkeypatch.setattr(moc, "MIGRATION_EVENTS_PATH", gh / "migration_events.jsonl")
    monkeypatch.setattr(moc, "OBSERVABILITY_META_PATH", gh / "observability_meta.yaml")
    return gh


def _append_gate(path: Path, status: str, gate_id: str = "M0_TO_M1") -> None:
    row = {
        "phase": "M0_ACTIVE",
        "gate_id": gate_id,
        "status": status,
        "blockers": ["test blocker"] if status == "NO_GO" else [],
        "warnings": [],
        "active_critical_risks": [],
        "active_high_risks": [],
        "evaluated_at": "2026-06-03T20:00:00Z",
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")


def test_event_stream_includes_gate_and_risk(obs_github: Path) -> None:
    _append_gate(obs_github / "gate_evaluation_history.jsonl", "DEGRADED")
    events = moc.build_event_stream()
    types = {e.event_type for e in events}
    assert "GATE_RESULT" in types
    assert "RISK_TRIGGER" in types


def test_systemic_gate_failure_rule(obs_github: Path) -> None:
    hist = obs_github / "gate_evaluation_history.jsonl"
    for _ in range(3):
        _append_gate(hist, "NO_GO")

    from scripts.event_rules_engine import apply_rules

    notes = apply_rules(dry_run=True)
    assert any(n.event_type == "SYSTEMIC_GATE_FAILURE" for n in notes)


def test_repeated_gate_failure_escalation(obs_github: Path) -> None:
    hist = obs_github / "gate_evaluation_history.jsonl"
    _append_gate(hist, "NO_GO")
    _append_gate(hist, "NO_GO")

    from scripts.event_rules_engine import apply_rules

    notes = apply_rules(dry_run=True)
    assert any(n.event_type == "GATE_ESCALATION" for n in notes)


def test_critical_risk_opens_incident(obs_github: Path) -> None:
    from scripts.event_rules_engine import apply_rules

    apply_rules(dry_run=False)
    active = moc.active_incidents()
    assert any(i.get("rule") == "critical_risk_detected" for i in active)


def test_ack_incident(obs_github: Path) -> None:
    inc = moc.open_incident(
        phase="M0_ACTIVE",
        gate="M0_TO_M1",
        failure_reason="test",
        severity="HIGH",
        rule="test_rule",
    )
    ack = moc.acknowledge_incident(inc["incident_id"])
    assert ack is not None
    assert ack["acknowledged"] is True


def test_dashboard_snapshot_written(obs_github: Path) -> None:
    _append_gate(obs_github / "gate_evaluation_history.jsonl", "NO_GO")
    path = moc.write_gate_status_snapshot()
    text = path.read_text(encoding="utf-8")
    assert "Event Stream (last 10)" in text
    assert "Risk Heat Indicator" in text
    assert "M0_TO_M1" in text


def test_rollback_proposal_event(obs_github: Path) -> None:
    (obs_github / "rollback_proposals.yaml").write_text(
        "proposals:\n"
        "  - id: RB-001\n"
        "    timestamp: 2026-06-03T21:00:00Z\n"
        "    gate: M1_TO_M2\n"
        "    reason: dual-write mismatch\n"
        "    recommended_action: pause flag rollout\n"
        "    impacted_issues: [P1-E01-08]\n",
        encoding="utf-8",
    )
    from scripts.event_rules_engine import apply_rules

    notes = apply_rules(dry_run=True)
    assert any(n.event_type == "ROLLBACK_PROPOSAL" for n in notes)
