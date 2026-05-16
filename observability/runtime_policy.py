"""Deterministic runtime policies and guardrail validation (stdlib, inspection-only)."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Literal

from observability.runtime_baseline import RUNTIME_DURATION_WARNING_THRESHOLD_SEC
from observability.runtime_history import HISTORY_LIMIT
from observability.runtime_schema import (
    CURRENT_RUNTIME_SCHEMA_VERSION,
    get_supported_schema_versions,
)

PolicyStatus = Literal["OK", "WARNING", "FAIL"]

RUNTIME_POLICY_REL = Path("runtime") / "runtime_policy.json"
POLICY_REPORT_REL = Path("runtime") / "policy_report.json"

POLICY_SCHEMA_VERSION = CURRENT_RUNTIME_SCHEMA_VERSION

REQUIRED_RUNTIME_POLICIES: tuple[str, ...] = (
    "bounded_history_limit",
    "latest_only_artifacts",
    "single_writer_runtime",
    "offline_inspection_only",
    "deterministic_artifact_generation",
    "single_node_runtime",
)

REQUIRED_GUARDRAILS: tuple[str, ...] = (
    "no_distributed_coordination",
    "no_background_daemons",
    "no_unbounded_retention",
    "no_runtime_mutation_during_validation",
)

UNSUPPORTED_POLICY_DOMAINS: tuple[str, ...] = (
    "distributed_execution",
    "orchestration_engines",
    "dynamic_scaling",
    "telemetry_platforms",
    "runtime_mutation_during_validation",
)

CANONICAL_POLICY_CONSTRAINTS: dict[str, int | float] = {
    "max_history_entries": HISTORY_LIMIT,
    "max_supported_schema_version": max(get_supported_schema_versions()),
    "runtime_duration_warning_threshold_sec": RUNTIME_DURATION_WARNING_THRESHOLD_SEC,
}

KNOWN_OPTIONAL_POLICIES: frozenset[str] = frozenset({"restart_safe_runtime"})

POLICY_KEY_ORDER: tuple[str, ...] = (
    "generated_at",
    "policy_constraints",
    "policy_status",
    "runtime_guardrails",
    "runtime_policies",
    "schema_version",
)

REPORT_KEY_ORDER: tuple[str, ...] = (
    "constraint_violations",
    "generated_at",
    "guardrail_violations",
    "policy_failures",
    "policy_present",
    "policy_validation_status",
    "policy_warnings",
    "schema_version",
)


def default_runtime_policy_path(base_dir: Path) -> Path:
    return base_dir.expanduser().resolve() / RUNTIME_POLICY_REL


def default_policy_report_path(base_dir: Path) -> Path:
    return base_dir.expanduser().resolve() / POLICY_REPORT_REL


def _utc_now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _default_runtime_policies() -> dict[str, bool | int]:
    return {
        "bounded_history_limit": HISTORY_LIMIT,
        "latest_only_artifacts": True,
        "single_writer_runtime": True,
        "offline_inspection_only": True,
        "deterministic_artifact_generation": True,
        "single_node_runtime": True,
    }


def build_runtime_policy(output_dir: Path | None = None) -> dict[str, Any]:
    """Build canonical runtime policy (deterministic operational guardrails)."""
    _ = output_dir
    policy: dict[str, Any] = {
        "schema_version": POLICY_SCHEMA_VERSION,
        "generated_at": _utc_now_iso(),
        "policy_status": "OK",
        "runtime_policies": _default_runtime_policies(),
        "runtime_guardrails": sorted(REQUIRED_GUARDRAILS),
        "policy_constraints": dict(CANONICAL_POLICY_CONSTRAINTS),
    }
    validation = validate_runtime_policy(policy, output_dir)
    policy["policy_status"] = validation["policy_validation_status"]
    return {k: policy[k] for k in POLICY_KEY_ORDER}


def load_runtime_policy(path: Path) -> dict[str, Any] | None:
    data = _load_json(path.expanduser().resolve())
    if data is None:
        return None
    return {k: data[k] for k in POLICY_KEY_ORDER if k in data}


def _validate_schema_version(raw: Any) -> tuple[PolicyStatus, list[str]]:
    if raw is None:
        return "FAIL", ["missing_schema_version"]
    if isinstance(raw, bool) or not isinstance(raw, int) or raw <= 0:
        return "FAIL", ["malformed_schema_version"]
    if raw != POLICY_SCHEMA_VERSION:
        return "WARNING", [f"schema_version_mismatch:{raw}"]
    return "OK", []


def _validate_constraints(constraints: dict[str, Any]) -> tuple[list[str], list[str], list[str]]:
    failures: list[str] = []
    warnings: list[str] = []
    violations: list[str] = []

    if not isinstance(constraints, dict):
        return ["invalid_policy_constraints:type"], [], []

    for key, expected in CANONICAL_POLICY_CONSTRAINTS.items():
        if key not in constraints:
            violations.append(f"missing_constraint:{key}")
            continue
        actual = constraints[key]
        try:
            if isinstance(expected, float):
                ok = abs(float(actual) - float(expected)) < 1e-6
            else:
                ok = int(actual) == int(expected)
        except (TypeError, ValueError):
            ok = False
        if not ok:
            failures.append(f"invalid_constraint_value:{key}")

    for key in sorted(constraints):
        if key not in CANONICAL_POLICY_CONSTRAINTS:
            warnings.append(f"unknown_optional_constraint:{key}")

    return failures, warnings, violations


def validate_runtime_policy(
    policy: dict[str, Any],
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Validate policy document and optional cross-check against on-disk runtime artifacts."""
    failures: list[str] = []
    warnings: list[str] = []
    guardrail_violations: list[str] = []
    constraint_violations: list[str] = []

    st, msgs = _validate_schema_version(policy.get("schema_version"))
    if st == "FAIL":
        failures.extend(msgs)
    elif st == "WARNING":
        warnings.extend(msgs)

    policies = policy.get("runtime_policies")
    if not isinstance(policies, dict):
        failures.append("missing_required_policies:runtime_policies")
        policies = {}

    for key in REQUIRED_RUNTIME_POLICIES:
        val = policies.get(key)
        if key == "bounded_history_limit":
            try:
                if int(val) != HISTORY_LIMIT:
                    failures.append(f"unsupported_policy_value:{key}")
            except (TypeError, ValueError):
                failures.append(f"missing_required_policy:{key}")
        elif val is not True:
            failures.append(f"missing_required_policy:{key}")

    for key in sorted(policies):
        if key not in REQUIRED_RUNTIME_POLICIES and key not in KNOWN_OPTIONAL_POLICIES:
            warnings.append(f"unknown_optional_policy:{key}")

    guardrails = policy.get("runtime_guardrails") or []
    if not isinstance(guardrails, list):
        guardrails = []
    for req in REQUIRED_GUARDRAILS:
        if req not in guardrails:
            guardrail_violations.append(f"missing_guardrail:{req}")

    for domain in UNSUPPORTED_POLICY_DOMAINS:
        if domain in guardrails or domain in policies:
            failures.append(f"unsupported_policy_domain:{domain}")

    c_fail, c_warn, c_viol = _validate_constraints(policy.get("policy_constraints") or {})
    failures.extend(c_fail)
    warnings.extend(c_warn)
    constraint_violations.extend(c_viol)

    if output_dir is not None:
        failures, warnings, guardrail_violations = _cross_check_runtime_state(
            output_dir,
            policy,
            failures,
            warnings,
            guardrail_violations,
        )

    failures = sorted(set(failures))
    warnings = sorted(set(warnings))
    guardrail_violations = sorted(set(guardrail_violations))
    constraint_violations = sorted(set(constraint_violations))

    if failures or guardrail_violations:
        status: PolicyStatus = "FAIL"
    elif warnings or constraint_violations:
        status = "WARNING"
    else:
        status = "OK"

    return {
        "policy_validation_status": status,
        "guardrail_violations": guardrail_violations,
        "constraint_violations": constraint_violations,
        "policy_warnings": warnings,
        "policy_failures": failures,
    }


def _cross_check_runtime_state(
    output_dir: Path,
    policy: dict[str, Any],
    failures: list[str],
    warnings: list[str],
    guardrail_violations: list[str],
) -> tuple[list[str], list[str], list[str]]:
    """Lightweight inspection of artifacts vs policy (no host autodiscovery)."""
    base = output_dir.expanduser().resolve()
    hist = _load_json(base / "runtime" / "qualification_history.json")
    if hist is not None:
        limit = int(hist.get("history_limit") or 0)
        expected = int(
            (policy.get("runtime_policies") or {}).get("bounded_history_limit") or HISTORY_LIMIT,
        )
        if limit > expected:
            failures.append("runtime_configuration_violation:history_limit_exceeded")
    compat = _load_json(base / "runtime" / "compatibility_report.json")
    if compat:
        for _name, ver in (compat.get("artifact_versions") or {}).items():
            try:
                if int(ver) > int(CANONICAL_POLICY_CONSTRAINTS["max_supported_schema_version"]):
                    failures.append("runtime_configuration_violation:schema_version_exceeded")
                    break
            except (TypeError, ValueError):
                pass
    caps = _load_json(base / "runtime" / "runtime_capabilities.json")
    if caps:
        model = str(caps.get("runtime_model") or "")
        if model != "single-node" and (policy.get("runtime_policies") or {}).get(
            "single_node_runtime"
        ):
            failures.append("runtime_configuration_violation:non_single_node_capability")
    if os.getenv("NEWSROOM_ENABLE_RUNTIME_DAEMONS", "").strip().lower() in ("1", "true", "yes"):
        guardrail_violations.append("violation:no_background_daemons")
    return failures, warnings, guardrail_violations


def build_policy_report(
    output_dir: Path,
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build policy validation report."""
    base = output_dir.expanduser().resolve()
    policy_path = default_runtime_policy_path(base)
    prof = policy
    policy_present = False
    if prof is None and policy_path.is_file():
        prof = load_runtime_policy(policy_path)
        policy_present = prof is not None
    if prof is None:
        prof = build_runtime_policy(base)

    validation = validate_runtime_policy(prof, base)

    report: dict[str, Any] = {
        "schema_version": POLICY_SCHEMA_VERSION,
        "generated_at": _utc_now_iso(),
        "policy_validation_status": validation["policy_validation_status"],
        "policy_present": policy_present,
        "guardrail_violations": validation["guardrail_violations"],
        "constraint_violations": validation["constraint_violations"],
        "policy_warnings": validation["policy_warnings"],
        "policy_failures": validation["policy_failures"],
    }
    return {k: report[k] for k in REPORT_KEY_ORDER}


def write_runtime_policy(path: Path, policy: dict[str, Any]) -> Path:
    dest = path.expanduser().resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)
    ordered = {k: policy[k] for k in POLICY_KEY_ORDER if k in policy}
    payload = json.dumps(ordered, indent=2, sort_keys=True, default=str) + "\n"
    tmp = dest.with_name(dest.name + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, dest)
    return dest


def write_policy_report(path: Path, report: dict[str, Any]) -> Path:
    dest = path.expanduser().resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)
    ordered = {k: report[k] for k in REPORT_KEY_ORDER if k in report}
    payload = json.dumps(ordered, indent=2, sort_keys=True, default=str) + "\n"
    tmp = dest.with_name(dest.name + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, dest)
    return dest


def update_runtime_policy(output_dir: Path) -> tuple[Path, Path]:
    """Write policy and validation report (atomic, latest-only)."""
    base = output_dir.expanduser().resolve()
    policy = build_runtime_policy(base)
    prof_path = write_runtime_policy(default_runtime_policy_path(base), policy)
    report = build_policy_report(base, policy=policy)
    rep_path = write_policy_report(default_policy_report_path(base), report)
    return prof_path, rep_path


def strict_policy_exit_code(report: dict[str, Any], *, strict: bool) -> int:
    st = str(report.get("policy_validation_status") or "FAIL")
    if st == "FAIL":
        return 1
    if strict and st != "OK":
        return 1
    return 0


def render_policy_summary(policy: dict[str, Any], report: dict[str, Any]) -> str:
    lines = [
        "Runtime policy inspection summary",
        "",
        "Runtime policies are operational inspection artifacts, not enforcement systems.",
        "",
        f"Policy validation status: {report.get('policy_validation_status')}",
        f"Policy status: {policy.get('policy_status')}",
        f"Policy present on disk: {report.get('policy_present')}",
    ]
    guardrails = policy.get("runtime_guardrails") or []
    if guardrails:
        lines.append("")
        lines.append("Runtime guardrails:")
        for g in guardrails:
            lines.append(f"  {g}")
    for key in (
        "policy_failures",
        "policy_warnings",
        "guardrail_violations",
        "constraint_violations",
    ):
        items = report.get(key) or []
        if items:
            lines.append(f"{key}: {', '.join(items)}")
    lines.append("")
    lines.append("Unsupported policy domains (explicit non-goals):")
    for d in UNSUPPORTED_POLICY_DOMAINS:
        lines.append(f"  {d}")
    return "\n".join(lines) + "\n"
