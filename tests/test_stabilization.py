"""Tests for ADR-037 bounded stabilization loop."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import healing_common as hc
from scripts import migration_observability_common as moc
from scripts import stabilization_common as sc
from scripts.failure_analyzer import analyze
from scripts.stabilization_decision_engine import decide
from scripts.stabilization_executor import execute_actions
from scripts.stabilization_policy_engine import evaluate_policy


@pytest.fixture()
def stab_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    gh = tmp_path / "github"
    gh.mkdir()
    (gh / "migration_state.txt").write_text("M0_ACTIVE\n", encoding="utf-8")
    (gh / "risk_registry.yaml").write_text(
        "risks:\n"
        "  - id: RISK-007\n"
        "    title: Dual-write schema drift\n"
        "    level: CRITICAL\n"
        "    status: active\n"
        "    impacted_issues: [P1-E04-02]\n",
        encoding="utf-8",
    )
    (gh / "incidents_store.yaml").write_text(
        "incidents:\n"
        "  - incident_id: INC-STAB-001\n"
        "    failure_reason: idempotency key collision in publish\n"
        "    impacted_issues: [P1-E01-03]\n"
        "    severity: MEDIUM\n"
        "    phase: M0_ACTIVE\n"
        "    gate: M0_TO_M1\n"
        "    status: OPEN\n"
        "    acknowledged: false\n"
        "    resolved: false\n"
        "    rule: test\n",
        encoding="utf-8",
    )
    (gh / "healing_registry.yaml").write_text("patterns: []\n", encoding="utf-8")
    (gh / "healing_proposals.yaml").write_text("proposals: []\n", encoding="utf-8")
    (gh / "rollback_proposals.yaml").write_text("proposals: []\n", encoding="utf-8")
    (gh / "stabilization_safety_guard.yaml").write_text(
        (Path(__file__).resolve().parents[1] / "github/stabilization_safety_guard.yaml").read_text(),
        encoding="utf-8",
    )
    (gh / "stabilization_metrics.yaml").write_text("totals: {}\nrates: {}\nmttr:\n  samples: []\nrecent_actions: []\n", encoding="utf-8")
    (gh / "gate_evaluation_history.jsonl").write_text(
        json.dumps(
            {
                "phase": "M0_ACTIVE",
                "gate_id": "M0_TO_M1",
                "status": "DEGRADED",
                "blockers": [],
                "warnings": ["idempotency check lag"],
                "evaluated_at": "2026-06-03T20:00:00Z",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (gh / "migration_events.jsonl").write_text("", encoding="utf-8")
    (gh / "stabilization_events.jsonl").write_text("", encoding="utf-8")

    sandbox = tmp_path / "var" / "stabilization_sandbox"
    monkeypatch.setattr(sc, "STABILIZATION_SANDBOX_DIR", sandbox)

    for mod in (moc, hc, sc):
        monkeypatch.setattr(mod, "GITHUB_DIR", gh)
        if hasattr(mod, "GATE_HISTORY_PATH"):
            monkeypatch.setattr(mod, "GATE_HISTORY_PATH", gh / "gate_evaluation_history.jsonl")
        if hasattr(mod, "MIGRATION_EVENTS_PATH"):
            monkeypatch.setattr(mod, "MIGRATION_EVENTS_PATH", gh / "migration_events.jsonl")
        if hasattr(mod, "MIGRATION_STATE_PATH"):
            monkeypatch.setattr(mod, "MIGRATION_STATE_PATH", gh / "migration_state.txt")
        if hasattr(mod, "RISK_REGISTRY_PATH"):
            monkeypatch.setattr(mod, "RISK_REGISTRY_PATH", gh / "risk_registry.yaml")
        if hasattr(mod, "INCIDENTS_STORE_PATH"):
            monkeypatch.setattr(mod, "INCIDENTS_STORE_PATH", gh / "incidents_store.yaml")
        if hasattr(mod, "STABILIZATION_GUARD_PATH"):
            monkeypatch.setattr(mod, "STABILIZATION_GUARD_PATH", gh / "stabilization_safety_guard.yaml")
        if hasattr(mod, "STABILIZATION_METRICS_PATH"):
            monkeypatch.setattr(mod, "STABILIZATION_METRICS_PATH", gh / "stabilization_metrics.yaml")
        if hasattr(mod, "STABILIZATION_LOG_PATH"):
            monkeypatch.setattr(mod, "STABILIZATION_LOG_PATH", gh / "stabilization_events.jsonl")

    return gh


def test_policy_low_confidence_suggest_only() -> None:
    policy = evaluate_policy(confidence=0.45, failure_type="idempotency_failure")
    assert policy["mode"] == sc.POLICY_SUGGEST


def test_policy_high_confidence_idempotency(stab_env: Path) -> None:
    policy = evaluate_policy(confidence=0.95, failure_type="idempotency_failure", risk_level="MEDIUM")
    assert policy["mode"] == sc.POLICY_AUTO_STABILIZE
    assert "rerun_idempotent_job" in policy["allowed_actions"]


def test_critical_risk_blocks_auto_stabilize(stab_env: Path) -> None:
    analysis = analyze(incident_id="INC-STAB-001")
    # Override to idempotency with high confidence for policy path
    analysis.failure_type = "idempotency_failure"
    analysis.confidence = 0.95
    analysis.severity = "MEDIUM"
    from scripts.remediation_planner import build_plan

    decision = decide(analysis, build_plan(analysis))
    # CRITICAL RISK-007 still active in registry → hard stop
    assert decision.decision != sc.POLICY_AUTO_STABILIZE
    assert decision.guard_blocked or decision.decision in {sc.POLICY_SUGGEST, sc.POLICY_DRAFT_PR}


def test_executor_whitelist_only(stab_env: Path) -> None:
    results = execute_actions(
        ["rerun_idempotent_job", "force_prod_write"],
        incident_id="INC-STAB-001",
        issue_key="P1-E01-03",
        dry_run=True,
    )
    statuses = {r.action: r.status for r in results}
    assert statuses["rerun_idempotent_job"] == "DRY_RUN"
    assert statuses["force_prod_write"] == "BLOCKED"


def test_rate_limit_blocks(stab_env: Path) -> None:
    for _ in range(3):
        execute_actions(["reset_transient_cache"], issue_key="P1-E01-03", dry_run=True)
    assert sc.rate_limit_exceeded("P1-E01-03") is True


def test_loop_orchestrator_dry_run(stab_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts import migration_observability_common as moc_mod

    monkeypatch.setattr(moc_mod, "PROJECT_ROOT", stab_env.parent)
    monkeypatch.setattr(hc, "HEALING_ARTIFACTS_DIR", stab_env / "healing-artifacts")
    from scripts.stabilization_loop_orchestrator import run_loop

    result = run_loop(incident_id="INC-STAB-001", dry_run=True, force=True)
    assert not result.get("skipped")
    assert "decision" in result
    assert "analysis" in result
