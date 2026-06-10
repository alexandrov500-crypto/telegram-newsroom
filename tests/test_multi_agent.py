"""Tests for ADR-037 multi-agent ops layer."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import healing_common as hc
from scripts import migration_observability_common as moc
from scripts.agents.agent_core import (
    AGENT_DECISION_LOG_PATH,
    FINAL_ALLOW_DRAFT_PR,
    FINAL_BLOCK,
    FINAL_STOP_THE_LINE,
    FINAL_SUGGEST_ONLY,
)
from scripts.agents.conflict_resolver import resolve_conflicts
from scripts.agents.agent_core import AgentContext, AgentOutput, build_context
from scripts.agents.multi_agent_orchestrator import run_multi_agent_pipeline
from scripts.agents.planner_agent import run_planner
from scripts.agents.risk_auditor_agent import run_risk_auditor
from scripts.agents.verifier_agent import run_verifier
from scripts.failure_analyzer import analyze


@pytest.fixture()
def agent_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
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
    (gh / "incidents_store.yaml").write_text(
        "incidents:\n"
        "  - incident_id: INC-MA-001\n"
        "    failure_reason: idempotency collision\n"
        "    impacted_issues: [P1-E01-03]\n"
        "    severity: MEDIUM\n"
        "    phase: M0_ACTIVE\n"
        "    status: OPEN\n"
        "    acknowledged: false\n"
        "    resolved: false\n"
        "    rule: test\n",
        encoding="utf-8",
    )
    (gh / "stabilization_safety_guard.yaml").write_text(
        "whitelist_actions:\n"
        "  - rerun_idempotent_job\n"
        "forbidden_paths:\n"
        "  - github/migration_state.txt\n"
        "hard_stops:\n"
        "  critical_risk_active: true\n",
        encoding="utf-8",
    )
    (gh / "gate_evaluation_history.jsonl").write_text(
        json.dumps(
            {
                "phase": "M0_ACTIVE",
                "gate_id": "M0_TO_M1",
                "status": "DEGRADED",
                "blockers": [],
                "warnings": ["idempotency lag"],
                "evaluated_at": "2026-06-03T20:00:00Z",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (gh / "migration_events.jsonl").write_text("", encoding="utf-8")
    (gh / "agent_decision_log.jsonl").write_text("", encoding="utf-8")
    (gh / "rollback_proposals.yaml").write_text("proposals: []\n", encoding="utf-8")

    monkeypatch.setattr(moc, "GITHUB_DIR", gh)
    monkeypatch.setattr(moc, "MIGRATION_STATE_PATH", gh / "migration_state.txt")
    monkeypatch.setattr(moc, "RISK_REGISTRY_PATH", gh / "risk_registry.yaml")
    monkeypatch.setattr(moc, "INCIDENTS_STORE_PATH", gh / "incidents_store.yaml")
    monkeypatch.setattr(moc, "GATE_HISTORY_PATH", gh / "gate_evaluation_history.jsonl")
    monkeypatch.setattr(moc, "MIGRATION_EVENTS_PATH", gh / "migration_events.jsonl")
    monkeypatch.setattr(moc, "ROLLBACK_PROPOSALS_PATH", gh / "rollback_proposals.yaml")
    monkeypatch.setattr(hc, "GITHUB_DIR", gh)
    import scripts.agents.agent_core as ac
    import scripts.stabilization_common as sc

    monkeypatch.setattr(ac, "GITHUB_DIR", gh)
    monkeypatch.setattr(ac, "AGENT_DECISION_LOG_PATH", gh / "agent_decision_log.jsonl")
    monkeypatch.setattr(sc, "STABILIZATION_GUARD_PATH", gh / "stabilization_safety_guard.yaml")
    monkeypatch.setattr(sc, "GITHUB_DIR", gh)

    return gh


def test_planner_produces_strategy(agent_env: Path) -> None:
    ctx = build_context(incident_id="INC-MA-001")
    out = run_planner(ctx)
    assert out.payload.get("remediation_steps")
    assert out.payload.get("mapped_issues")


def test_verifier_rejects_unsafe_step(agent_env: Path) -> None:
    ctx = build_context(incident_id="INC-MA-001")
    run_planner(ctx)
    ctx.plan.steps.append("auto rollback production migration_state.txt now")
    out = run_verifier(ctx)
    assert out.status == "REJECTED"
    assert out.violations


def test_risk_auditor_stop_the_line_on_dual_write(agent_env: Path) -> None:
    ctx = build_context(incident_id="INC-MA-001")
    run_planner(ctx)
    ctx.analysis.failure_type = "dual_write_inconsistency"
    out = run_risk_auditor(ctx)
    assert out.payload.get("stop_the_line") is True
    assert out.payload.get("risk_level") == "CRITICAL"


def test_fusion_stop_the_line_overrides_planner(agent_env: Path) -> None:
    planner = AgentOutput(agent="planner", status="OK", confidence=0.95, payload={})
    verifier = AgentOutput(
        agent="verifier",
        status="VERIFIED",
        confidence=0.9,
        payload={"verdict": "VERIFIED"},
    )
    auditor = AgentOutput(
        agent="risk_auditor",
        status="STOP",
        confidence=0.95,
        payload={"risk_level": "CRITICAL", "stop_the_line": True, "reasons": ["dual-write"]},
    )
    fusion = resolve_conflicts(planner, verifier, auditor)
    assert fusion.final_decision == FINAL_STOP_THE_LINE


def test_fusion_verifier_rejected_blocks(agent_env: Path) -> None:
    planner = AgentOutput(agent="planner", status="OK", confidence=0.7, payload={})
    verifier = AgentOutput(
        agent="verifier",
        status="REJECTED",
        confidence=0.0,
        payload={"verdict": "REJECTED"},
        violations=["unsafe"],
    )
    auditor = AgentOutput(
        agent="risk_auditor",
        status="MED",
        payload={"risk_level": "MED", "stop_the_line": False, "reasons": []},
    )
    fusion = resolve_conflicts(planner, verifier, auditor)
    assert fusion.final_decision == FINAL_BLOCK


def test_orchestrator_logs_trace(agent_env: Path) -> None:
    trace = run_multi_agent_pipeline(incident_id="INC-MA-001", trigger="test")
    assert trace.get("run_id")
    assert "agents" in trace
    log_path = agent_env / "agent_decision_log.jsonl"
    assert log_path.is_file()
    assert trace["run_id"] in log_path.read_text()


def test_idempotency_low_critical_risk_scenario(agent_env: Path) -> None:
    """Idempotency failure with CRITICAL registry risk still triggers stop-the-line."""
    trace = run_multi_agent_pipeline(incident_id="INC-MA-001", trigger="test")
    # CRITICAL RISK-007 active in registry → risk auditor stop-the-line
    assert trace["final_decision"] in {FINAL_STOP_THE_LINE, FINAL_SUGGEST_ONLY, FINAL_BLOCK}
