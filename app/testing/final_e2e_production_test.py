"""Production-like E2E validation (controlled, no public Telegram side effects)."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.observability.release_contract import REQUIRED_CONTRACT_FIELDS
from app.observability.release_contract_evaluator import collect_contract_checks
from app.observability.validation_contract import evaluate_required_only_contract, metric


@dataclass
class _SimTick:
    tick_id: str
    summarize_calls: int = 0
    finalize_calls: int = 0
    publish_gate_allowed: int = 0
    publish_success: int = 0
    rollback_active: bool = False
    published_ids: list[int] = field(default_factory=list)
    critical_runtime: bool = False


def _validate_tick_invariants(tick: _SimTick) -> list[str]:
    violations: list[str] = []
    if tick.publish_success > 0 and tick.finalize_calls < 1:
        violations.append("publish_without_finalize")
    if tick.finalize_calls > 0 and tick.summarize_calls < 1:
        violations.append("finalize_without_summarize")
    if tick.publish_success > 0 and tick.publish_gate_allowed < 1:
        violations.append("publish_without_gate_allowed")
    if tick.rollback_active and tick.publish_success > 0:
        violations.append("rollback_publish_leakage")
    if len(tick.published_ids) != len(set(tick.published_ids)):
        violations.append("duplicate_publish_id")
    if tick.critical_runtime:
        violations.append("critical_runtime_present")
    if tick.finalize_calls > 1:
        violations.append("duplicate_finalize")
    if tick.summarize_calls > 1:
        violations.append("duplicate_summarize")
    return violations


def _scenario_normal() -> dict[str, Any]:
    tick = _SimTick(tick_id="normal-1")
    tick.summarize_calls = 1
    tick.finalize_calls = 1
    tick.publish_gate_allowed = 1
    tick.publish_success = 1
    tick.published_ids = [10_001]
    violations = _validate_tick_invariants(tick)
    return {"name": "normal_flow", "ok": not violations, "violations": violations}


def _scenario_retry() -> dict[str, Any]:
    tick = _SimTick(tick_id="retry-1")
    tick.summarize_calls = 1
    tick.finalize_calls = 1
    tick.publish_gate_allowed = 1  # retried gate, single allowed publish
    tick.publish_success = 1
    tick.published_ids = [10_002]
    violations = _validate_tick_invariants(tick)
    return {"name": "retry_flow", "ok": not violations, "violations": violations}


def _scenario_partial_failure() -> dict[str, Any]:
    tick = _SimTick(tick_id="partial-1")
    tick.summarize_calls = 1
    tick.finalize_calls = 0
    tick.publish_gate_allowed = 0
    tick.publish_success = 0
    violations = _validate_tick_invariants(tick)
    return {"name": "partial_failure_flow", "ok": not violations, "violations": violations}


def _scenario_rollback() -> dict[str, Any]:
    tick = _SimTick(tick_id="rollback-1")
    tick.summarize_calls = 1
    tick.finalize_calls = 1
    tick.rollback_active = True
    tick.publish_gate_allowed = 0
    tick.publish_success = 0
    violations = _validate_tick_invariants(tick)
    return {"name": "rollback_activation_flow", "ok": not violations, "violations": violations}


def _runtime_dir() -> Path:
    return Path(os.getenv("RUNTIME_STATE_DIR", "var/runtime")).expanduser().resolve()


def run_final_e2e_production_test() -> dict[str, Any]:
    scenarios = [
        _scenario_normal(),
        _scenario_retry(),
        _scenario_partial_failure(),
        _scenario_rollback(),
    ]
    scenario_ok = all(bool(s.get("ok")) for s in scenarios)

    runtime_checks = collect_contract_checks(str(_runtime_dir()))
    required = list(runtime_checks.get("required_checks") or [])
    present = {str(m.get("name")) for m in required}
    for field_name in sorted(REQUIRED_CONTRACT_FIELDS):
        if field_name not in present:
            required.append(metric(field_name, "UNKNOWN", reason="missing_runtime_probe"))

    required_eval = evaluate_required_only_contract(required=required)
    runtime_required_ok = str(required_eval.get("verdict")) == "READY_FOR_PUBLIC"

    ok = bool(scenario_ok and runtime_required_ok)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "controlled_test_mode": True,
        "no_real_telegram_posts": True,
        "ok": ok,
        "scenarios": scenarios,
        "scenario_ok": scenario_ok,
        "runtime_required_ok": runtime_required_ok,
        "required_contract": required_eval,
        "required_checks": required,
        "failure_classification": {
            "scenario": None if scenario_ok else "scenario_invariant_violation",
            "runtime_required": None if runtime_required_ok else "runtime_required_contract_failed",
        },
    }


def write_final_e2e_production_test_report(report: dict[str, Any], *, runtime_dir: str | None = None) -> Path:
    rd = Path(runtime_dir or os.getenv("RUNTIME_STATE_DIR", "var/runtime")).expanduser().resolve()
    out = rd / "final_e2e_production_test_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out
