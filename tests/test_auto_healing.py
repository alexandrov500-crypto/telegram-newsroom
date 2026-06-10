"""Tests for ADR-037 auto-healing layer."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import healing_common as hc
from scripts import migration_observability_common as moc
from scripts.failure_analyzer import analyze
from scripts.remediation_planner import build_plan


@pytest.fixture()
def healing_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    gh = tmp_path / "github"
    gh.mkdir()
    (gh / "migration_state.txt").write_text("M0_ACTIVE\n", encoding="utf-8")
    (gh / "risk_registry.yaml").write_text(
        "risks:\n"
        "  - id: RISK-007\n"
        "    title: Dual-write schema drift\n"
        "    level: CRITICAL\n"
        "    status: active\n"
        "    impacted_issues: [P1-E04-02, P1-E01-08]\n"
        "    mitigations:\n"
        "      - action: Align dual-write schema mapping\n"
        "        config: CONTENT_PACKAGE_DUAL_WRITE\n"
        "  - id: RISK-009\n"
        "    title: Story cluster persistence regression\n"
        "    level: HIGH\n"
        "    status: mitigated\n"
        "    impacted_issues: [P1-E01-07]\n",
        encoding="utf-8",
    )
    (gh / "incidents_store.yaml").write_text(
        "incidents:\n"
        "  - incident_id: INC-TEST-001\n"
        "    timestamp: '2026-06-03T20:00:00Z'\n"
        "    phase: M0_ACTIVE\n"
        "    gate: M0_TO_M1\n"
        "    status: OPEN\n"
        "    failure_reason: 'Critical risk active: RISK-007 — Dual-write schema drift'\n"
        "    impacted_issues: [P1-E04-02]\n"
        "    severity: CRITICAL\n"
        "    rule: critical_risk_detected\n"
        "    acknowledged: false\n"
        "    resolved: false\n",
        encoding="utf-8",
    )
    (gh / "rollback_proposals.yaml").write_text("proposals: []\n", encoding="utf-8")
    (gh / "healing_registry.yaml").write_text("patterns: []\n", encoding="utf-8")
    (gh / "healing_proposals.yaml").write_text("proposals: []\n", encoding="utf-8")
    (gh / "gate_evaluation_history.jsonl").write_text(
        json.dumps(
            {
                "phase": "M0_ACTIVE",
                "gate_id": "M0_TO_M1",
                "status": "NO_GO",
                "blockers": ["Active Critical risk: RISK-007"],
                "warnings": ["Offline: cannot verify P1-E01-01 on GitHub"],
                "active_critical_risks": ["RISK-007"],
                "evaluated_at": "2026-06-03T20:00:00Z",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (gh / "migration_events.jsonl").write_text("", encoding="utf-8")

    monkeypatch.setattr(moc, "GITHUB_DIR", gh)
    monkeypatch.setattr(moc, "MIGRATION_STATE_PATH", gh / "migration_state.txt")
    monkeypatch.setattr(moc, "RISK_REGISTRY_PATH", gh / "risk_registry.yaml")
    monkeypatch.setattr(moc, "INCIDENTS_STORE_PATH", gh / "incidents_store.yaml")
    monkeypatch.setattr(moc, "ROLLBACK_PROPOSALS_PATH", gh / "rollback_proposals.yaml")
    monkeypatch.setattr(moc, "GATE_HISTORY_PATH", gh / "gate_evaluation_history.jsonl")
    monkeypatch.setattr(moc, "MIGRATION_EVENTS_PATH", gh / "migration_events.jsonl")
    monkeypatch.setattr(moc, "GATE_SNAPSHOT_PATH", gh / "gate_status_snapshot.md")
    monkeypatch.setattr(moc, "OBSERVABILITY_META_PATH", gh / "observability_meta.yaml")
    monkeypatch.setattr(hc, "GITHUB_DIR", gh)
    monkeypatch.setattr(hc, "HEALING_REGISTRY_PATH", gh / "healing_registry.yaml")
    monkeypatch.setattr(hc, "HEALING_PROPOSALS_PATH", gh / "healing_proposals.yaml")
    monkeypatch.setattr(hc, "HEALING_ARTIFACTS_DIR", gh / "healing-artifacts")
    monkeypatch.setattr(hc, "GATE_HISTORY_PATH", gh / "gate_evaluation_history.jsonl")
    monkeypatch.setattr(hc, "MIGRATION_EVENTS_PATH", gh / "migration_events.jsonl")

    return gh


def test_failure_analyzer_dual_write(healing_env: Path) -> None:
    result = analyze(incident_id="INC-TEST-001")
    assert result.failure_type in {"dual_write_inconsistency", "schema_mismatch"}
    assert result.confidence >= 0.35
    assert "P1-E04-02" in result.affected_issues


def test_remediation_plan_includes_mitigations(healing_env: Path) -> None:
    analysis = analyze(incident_id="INC-TEST-001")
    plan = build_plan(analysis)
    assert plan.steps
    assert plan.pr_type in hc.PR_TYPES
    assert any("dual-write" in s.lower() or "Align" in s for s in plan.matched_mitigations + plan.steps)


def test_pr_generator_dry_run(healing_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts import migration_observability_common as moc_mod
    from scripts.pr_generator import create_draft_pr

    monkeypatch.setattr(moc_mod, "PROJECT_ROOT", healing_env.parent)
    analysis = analyze(incident_id="INC-TEST-001")
    plan = build_plan(analysis)
    proposal = create_draft_pr(analysis, plan, dry_run=True)
    assert proposal.proposal_id.startswith("HEAL-")
    art = hc.artifact_dir(proposal.proposal_id)
    assert (art / "failure_analysis.json").is_file()
    assert (art / "remediation_plan.md").is_file()


def test_orchestrator_dry_run(healing_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts import migration_observability_common as moc_mod
    from scripts.agents.agent_core import FINAL_ALLOW_DRAFT_PR
    from scripts.auto_healing_orchestrator import run_pipeline

    monkeypatch.setattr(moc_mod, "PROJECT_ROOT", healing_env.parent)
    monkeypatch.setattr(hc, "HEALING_ARTIFACTS_DIR", healing_env / "healing-artifacts")

    def _fake_ma(**kwargs: object) -> dict:
        return {
            "run_id": "MA-TEST",
            "final_decision": FINAL_ALLOW_DRAFT_PR,
            "allows_draft_pr": True,
            "blocked": False,
        }

    monkeypatch.setattr(
        "scripts.agents.multi_agent_orchestrator.run_multi_agent_pipeline",
        _fake_ma,
    )
    result = run_pipeline(incident_id="INC-TEST-001", dry_run=True, force=True)
    assert not result.get("skipped")
    assert result["proposal"]["proposal_id"].startswith("HEAL-")


def test_healing_registry_records_pattern(healing_env: Path) -> None:
    hc.record_healing_pattern(
        failure_signature_key="sig-1",
        matched_root_cause="dual_write_inconsistency",
        remediation_pattern="schema_fix",
        linked_pr="https://github.com/example/pull/1",
    )
    data = hc.read_healing_registry()
    assert len(data["patterns"]) == 1
    assert data["patterns"][0]["linked_prs"]


def test_active_healing_proposals(healing_env: Path) -> None:
    hc.append_healing_proposal(
        hc.HealingProposal(
            proposal_id="HEAL-TEST-001",
            created_at="2026-06-03T21:00:00Z",
            incident_id="INC-TEST-001",
            analysis_id="FA-TEST",
            plan_id="RP-TEST",
            pr_type="schema_fix",
            status="draft",
            pr_url="https://github.com/org/repo/pull/99",
            summary="test summary",
            recommended_actions=["step 1"],
        )
    )
    active = hc.active_healing_proposals()
    assert len(active) == 1
    assert active[0]["pr_url"]
