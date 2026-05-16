"""Smoke tests for runtime policy and guardrail validation."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from observability.runtime_history import HISTORY_LIMIT
from observability.runtime_policy import (
    CANONICAL_POLICY_CONSTRAINTS,
    POLICY_KEY_ORDER,
    REPORT_KEY_ORDER,
    REQUIRED_GUARDRAILS,
    build_policy_report,
    build_runtime_policy,
    load_runtime_policy,
    strict_policy_exit_code,
    update_runtime_policy,
    validate_runtime_policy,
    write_runtime_policy,
)

REPO = Path(__file__).resolve().parents[2]


def test_policy_schema() -> None:
    policy = build_runtime_policy(None)
    assert list(policy.keys()) == list(POLICY_KEY_ORDER)
    assert policy["schema_version"] == 1
    assert policy["runtime_policies"]["single_node_runtime"] is True
    assert sorted(policy["runtime_guardrails"]) == sorted(REQUIRED_GUARDRAILS)


def test_deterministic_policy_generation(tmp_path: Path) -> None:
    od = tmp_path / "out"
    od.mkdir()
    a = build_runtime_policy(od)
    b = build_runtime_policy(od)
    a.pop("generated_at", None)
    b.pop("generated_at", None)
    assert a == b


def test_required_guardrails_valid() -> None:
    policy = build_runtime_policy(None)
    validation = validate_runtime_policy(policy)
    assert validation["policy_validation_status"] == "OK"
    assert validation["guardrail_violations"] == []


def test_missing_guardrail_fail() -> None:
    policy = build_runtime_policy(None)
    policy = dict(policy)
    policy["runtime_guardrails"] = ["no_distributed_coordination"]
    validation = validate_runtime_policy(policy)
    assert validation["policy_validation_status"] == "FAIL"
    assert validation["guardrail_violations"]


def test_invalid_constraint_fail() -> None:
    policy = build_runtime_policy(None)
    policy = dict(policy)
    constraints = dict(policy["policy_constraints"])
    constraints["max_history_entries"] = 999
    policy["policy_constraints"] = constraints
    validation = validate_runtime_policy(policy)
    assert validation["policy_validation_status"] == "FAIL"
    assert any("invalid_constraint_value" in f for f in validation["policy_failures"])


def test_missing_required_policy_fail() -> None:
    policy = build_runtime_policy(None)
    policy = dict(policy)
    pols = dict(policy["runtime_policies"])
    pols["offline_inspection_only"] = False
    policy["runtime_policies"] = pols
    validation = validate_runtime_policy(policy)
    assert validation["policy_validation_status"] == "FAIL"


def test_policy_report_schema(tmp_path: Path) -> None:
    od = tmp_path / "out"
    od.mkdir()
    policy = build_runtime_policy(od)
    report = build_policy_report(od, policy=policy)
    assert list(report.keys()) == list(REPORT_KEY_ORDER)
    assert report["policy_validation_status"] == "OK"


def test_idempotent_report_fields(tmp_path: Path) -> None:
    od = tmp_path / "out"
    od.mkdir()
    policy = build_runtime_policy(od)
    a = build_policy_report(od, policy=policy)
    b = build_policy_report(od, policy=policy)
    a.pop("generated_at", None)
    b.pop("generated_at", None)
    assert a == b


def test_cross_check_history_limit(tmp_path: Path) -> None:
    od = tmp_path / "out"
    rt = od / "runtime"
    rt.mkdir(parents=True)
    (rt / "qualification_history.json").write_text(
        json.dumps({"schema_version": 1, "history_limit": 50, "entries": []}),
        encoding="utf-8",
    )
    policy = build_runtime_policy(od)
    validation = validate_runtime_policy(policy, od)
    assert validation["policy_validation_status"] == "FAIL"
    assert any("history_limit" in f for f in validation["policy_failures"])


def test_update_runtime_policy_writes(tmp_path: Path) -> None:
    od = tmp_path / "out"
    od.mkdir()
    pol_path, rep_path = update_runtime_policy(od)
    assert pol_path.is_file()
    assert rep_path.is_file()
    loaded = load_runtime_policy(pol_path)
    assert loaded is not None
    assert loaded["policy_constraints"]["max_history_entries"] == HISTORY_LIMIT
    assert loaded["policy_constraints"]["max_history_entries"] == CANONICAL_POLICY_CONSTRAINTS[
        "max_history_entries"
    ]


def test_strict_exit_codes() -> None:
    assert strict_policy_exit_code({"policy_validation_status": "OK"}, strict=True) == 0
    assert strict_policy_exit_code({"policy_validation_status": "WARNING"}, strict=True) == 1
    assert strict_policy_exit_code({"policy_validation_status": "FAIL"}, strict=False) == 1


def test_cli_inspect_policy_strict(tmp_path: Path) -> None:
    od = tmp_path / "out"
    rt = od / "runtime"
    rt.mkdir(parents=True)
    policy = build_runtime_policy(od)
    policy = dict(policy)
    policy["runtime_guardrails"] = []
    write_runtime_policy(rt / "runtime_policy.json", policy)
    proc = subprocess.run(
        [sys.executable, "-m", "newsroom.cli", "inspect-policy", "--path", str(od), "--strict"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
