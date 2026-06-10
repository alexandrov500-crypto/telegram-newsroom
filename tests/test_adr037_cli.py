"""Tests for ADR-037 unified CLI routing layer."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from scripts import adr037_cli
from scripts import migration_observability_common as moc


@pytest.fixture()
def cli_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    gh = tmp_path / "github"
    gh.mkdir()
    (gh / "migration_state.txt").write_text("M0_ACTIVE\n", encoding="utf-8")
    (gh / "gate_evaluation_history.jsonl").write_text("", encoding="utf-8")
    (gh / "migration_events.jsonl").write_text("", encoding="utf-8")
    (gh / "incidents_store.yaml").write_text("incidents: []\n", encoding="utf-8")
    (gh / "risk_registry.yaml").write_text("risks: []\n", encoding="utf-8")
    (gh / "rollback_proposals.yaml").write_text("proposals: []\n", encoding="utf-8")
    (gh / "observability_meta.yaml").write_text("{}\n", encoding="utf-8")
    (gh / "gate_status_snapshot.md").write_text("# gate\n", encoding="utf-8")
    (gh / "stabilization_safety_guard.yaml").write_text("hard_stops: {}\n", encoding="utf-8")
    (gh / "stabilization_metrics.yaml").write_text("totals: {}\nrates: {}\n", encoding="utf-8")
    (gh / "evolution_registry.yaml").write_text("pending_proposals: []\n", encoding="utf-8")
    (gh / "governance_memory.yaml").write_text("policy_changes: []\n", encoding="utf-8")
    (gh / "adversarial_verifier_patterns.yaml").write_text("suggested_patterns: []\n", encoding="utf-8")

    monkeypatch.setattr(moc, "GITHUB_DIR", gh)
    monkeypatch.setattr(moc, "MIGRATION_STATE_PATH", gh / "migration_state.txt")
    monkeypatch.setattr(moc, "GATE_HISTORY_PATH", gh / "gate_evaluation_history.jsonl")
    monkeypatch.setattr(moc, "MIGRATION_EVENTS_PATH", gh / "migration_events.jsonl")
    monkeypatch.setattr(moc, "INCIDENTS_STORE_PATH", gh / "incidents_store.yaml")
    monkeypatch.setattr(moc, "RISK_REGISTRY_PATH", gh / "risk_registry.yaml")
    monkeypatch.setattr(moc, "ROLLBACK_PROPOSALS_PATH", gh / "rollback_proposals.yaml")
    monkeypatch.setattr(moc, "GATE_SNAPSHOT_PATH", gh / "gate_status_snapshot.md")
    monkeypatch.setattr(moc, "PROJECT_ROOT", tmp_path)

    import scripts.governance.governance_common as gc

    monkeypatch.setattr(gc, "GITHUB_DIR", gh)
    monkeypatch.setattr(gc, "GOVERNANCE_MEMORY_PATH", gh / "governance_memory.yaml")
    monkeypatch.setattr(gc, "EVOLUTION_REGISTRY_PATH", gh / "evolution_registry.yaml")
    monkeypatch.setattr(gc, "STABILIZATION_METRICS_PATH", gh / "stabilization_metrics.yaml")
    monkeypatch.setattr(gc, "STABILIZATION_GUARD_PATH", gh / "stabilization_safety_guard.yaml")
    monkeypatch.setattr(gc, "VERIFIER_PATTERNS_PATH", gh / "adversarial_verifier_patterns.yaml")
    monkeypatch.setattr(gc, "RELIABILITY_REPORTS_DIR", gh / "reliability_reports")
    monkeypatch.setattr(gc, "GOVERNANCE_PROPOSALS_DIR", gh / "governance-proposals")
    monkeypatch.setattr(gc, "GOVERNANCE_RUNS_LOG", gh / "governance_runs.jsonl")

    return gh


def test_modes_defined() -> None:
    assert adr037_cli.MODES == frozenset(
        {"observe", "diagnose", "heal", "stabilize", "govern", "evolve", "simulate"}
    )
    assert adr037_cli.MODE_HANDLERS.keys() == adr037_cli.MODES


def test_status_snapshot(cli_env: Path) -> None:
    snap = adr037_cli.build_status_snapshot()
    assert snap["phase"] == "M0_ACTIVE"
    assert "allowed_actions" in snap


def test_main_status_command(cli_env: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = adr037_cli.main(["status"])
    assert code == 0
    assert "phase=M0_ACTIVE" in capsys.readouterr().out


def test_simulate_stub(cli_env: Path) -> None:
    result, code = adr037_cli.run_mode("simulate", adr037_cli.RunOptions())
    assert code == 0
    assert result["status"] == "not_implemented"
    assert result["production_mutated"] is False


def test_heal_dry_run_skips(cli_env: Path) -> None:
    result, code = adr037_cli.run_mode("heal", adr037_cli.RunOptions(dry_run=True))
    assert result["skipped"] is True
    assert code == 0


def test_observe_dry_run(cli_env: Path) -> None:
    with patch("scripts.event_rules_engine.apply_rules", return_value=[]):
        result, code = adr037_cli.run_mode("observe", adr037_cli.RunOptions(dry_run=True))
    assert result["mode"] == "observe"
    assert code == 0


def test_govern_mode(cli_env: Path) -> None:
    (cli_env / "adversarial_reports").mkdir()
    result, code = adr037_cli.run_mode("govern", adr037_cli.RunOptions())
    assert result["mode"] == "govern"
    assert "health_score" in result
    assert result["production_mutated"] is False
    assert code in {0, 2}
