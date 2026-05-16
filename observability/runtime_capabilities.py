"""Deterministic runtime capability profiles and deployment semantics (stdlib, inspection-only)."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Literal

from observability.runtime_schema import CURRENT_RUNTIME_SCHEMA_VERSION

CapabilityStatus = Literal["OK", "WARNING", "FAIL"]

RUNTIME_CAPABILITIES_REL = Path("runtime") / "runtime_capabilities.json"
CAPABILITY_REPORT_REL = Path("runtime") / "capability_report.json"

CAPABILITY_SCHEMA_VERSION = CURRENT_RUNTIME_SCHEMA_VERSION

CANONICAL_RUNTIME_MODEL = "single-node"
CANONICAL_DEPLOYMENT_PROFILE = "production-lite"

SUPPORTED_RUNTIME_MODELS: frozenset[str] = frozenset({CANONICAL_RUNTIME_MODEL})
SUPPORTED_DEPLOYMENT_PROFILES: frozenset[str] = frozenset({CANONICAL_DEPLOYMENT_PROFILE})

SUPPORTED_EXECUTION_MODES: tuple[str, ...] = (
    "manual",
    "nightly-cron",
    "systemd",
    "docker-compose-single-node",
    "offline-inspection",
)

UNSUPPORTED_EXECUTION_MODES: tuple[str, ...] = (
    "distributed-workers",
    "kubernetes-cluster",
    "multi-node-runtime",
    "shared-distributed-state",
    "central-telemetry-platform",
)

REQUIRED_RUNTIME_CHARACTERISTICS: tuple[str, ...] = (
    "bounded_state",
    "offline_inspection",
    "deterministic_artifacts",
    "shell_first_operations",
    "restart_safe_runtime",
)

REQUIRED_OPERATIONAL_CONSTRAINTS: tuple[str, ...] = (
    "single_writer_runtime",
    "no_distributed_coordination",
    "latest_only_artifacts",
)

KNOWN_RUNTIME_CHARACTERISTICS: frozenset[str] = frozenset(REQUIRED_RUNTIME_CHARACTERISTICS)

PROFILE_KEY_ORDER: tuple[str, ...] = (
    "capability_status",
    "deployment_profile",
    "generated_at",
    "operational_constraints",
    "runtime_characteristics",
    "runtime_model",
    "schema_version",
    "supported_execution_modes",
    "unsupported_execution_modes",
)

REPORT_KEY_ORDER: tuple[str, ...] = (
    "capability_failures",
    "capability_validation_status",
    "capability_warnings",
    "constraint_violations",
    "deployment_profile_supported",
    "generated_at",
    "profile_present",
    "runtime_model_supported",
    "schema_version",
)


def default_runtime_capabilities_path(base_dir: Path) -> Path:
    return base_dir.expanduser().resolve() / RUNTIME_CAPABILITIES_REL


def default_capability_report_path(base_dir: Path) -> Path:
    return base_dir.expanduser().resolve() / CAPABILITY_REPORT_REL


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


def _default_runtime_characteristics() -> dict[str, bool]:
    return {k: True for k in REQUIRED_RUNTIME_CHARACTERISTICS}


def _profile_capability_status(profile: dict[str, Any]) -> CapabilityStatus:
    validation = validate_runtime_capabilities(profile)
    return validation["capability_validation_status"]


def build_runtime_capability_profile(
    output_dir: Path | None = None,
    *,
    runtime_model: str = CANONICAL_RUNTIME_MODEL,
    deployment_profile: str = CANONICAL_DEPLOYMENT_PROFILE,
    execution_mode_hint: str | None = None,
) -> dict[str, Any]:
    """
    Build canonical capability profile (inspection metadata only).
    ``output_dir`` is accepted for API symmetry; profile content is deterministic.
    """
    _ = output_dir
    supported_modes = list(SUPPORTED_EXECUTION_MODES)
    if execution_mode_hint and execution_mode_hint in SUPPORTED_EXECUTION_MODES:
        if execution_mode_hint not in supported_modes:
            supported_modes.append(execution_mode_hint)

    profile: dict[str, Any] = {
        "schema_version": CAPABILITY_SCHEMA_VERSION,
        "generated_at": _utc_now_iso(),
        "capability_status": "OK",
        "runtime_model": runtime_model,
        "deployment_profile": deployment_profile,
        "supported_execution_modes": sorted(set(supported_modes)),
        "unsupported_execution_modes": sorted(UNSUPPORTED_EXECUTION_MODES),
        "runtime_characteristics": _default_runtime_characteristics(),
        "operational_constraints": sorted(REQUIRED_OPERATIONAL_CONSTRAINTS),
    }
    profile["capability_status"] = _profile_capability_status(profile)
    return {k: profile[k] for k in PROFILE_KEY_ORDER}


def load_runtime_capability_profile(path: Path) -> dict[str, Any] | None:
    data = _load_json(path.expanduser().resolve())
    if data is None:
        return None
    return {k: data[k] for k in PROFILE_KEY_ORDER if k in data}


def validate_runtime_capabilities(
    profile: dict[str, Any],
    *,
    execution_mode_hint: str | None = None,
) -> dict[str, Any]:
    """Validate profile against supported deployment semantics (read-only)."""
    failures: list[str] = []
    warnings: list[str] = []
    violations: list[str] = []

    st, msgs = _validate_schema_version(profile.get("schema_version"))
    if st == "FAIL":
        failures.extend(msgs)
    elif st == "WARNING":
        warnings.extend(msgs)

    model = str(profile.get("runtime_model") or "")
    deployment = str(profile.get("deployment_profile") or "")
    runtime_model_supported = model in SUPPORTED_RUNTIME_MODELS
    deployment_profile_supported = deployment in SUPPORTED_DEPLOYMENT_PROFILES

    if not runtime_model_supported:
        failures.append(f"unsupported_runtime_model:{model}")
    if not deployment_profile_supported:
        failures.append(f"invalid_deployment_profile:{deployment}")

    characteristics = profile.get("runtime_characteristics")
    if not isinstance(characteristics, dict):
        failures.append("missing_required_capabilities:runtime_characteristics")
        characteristics = {}

    for key in REQUIRED_RUNTIME_CHARACTERISTICS:
        if not characteristics.get(key):
            failures.append(f"missing_required_capability:{key}")

    for key in sorted(characteristics):
        if key not in KNOWN_RUNTIME_CHARACTERISTICS:
            warnings.append(f"unknown_optional_capability:{key}")

    constraints = profile.get("operational_constraints") or []
    if not isinstance(constraints, list):
        constraints = []
    for req in REQUIRED_OPERATIONAL_CONSTRAINTS:
        if req not in constraints:
            violations.append(f"missing_constraint:{req}")

    supported_modes = set(profile.get("supported_execution_modes") or [])
    for mode in UNSUPPORTED_EXECUTION_MODES:
        if mode in supported_modes:
            failures.append(f"unsupported_mode_listed_as_supported:{mode}")

    for mode in supported_modes:
        if mode not in SUPPORTED_EXECUTION_MODES and mode not in UNSUPPORTED_EXECUTION_MODES:
            warnings.append(f"unknown_optional_execution_mode:{mode}")

    hint = execution_mode_hint or os.getenv("NEWSROOM_EXECUTION_MODE", "").strip()
    if hint:
        if hint in UNSUPPORTED_EXECUTION_MODES:
            warnings.append(f"unsupported_execution_mode_hint:{hint}")
        elif hint not in SUPPORTED_EXECUTION_MODES:
            warnings.append(f"unknown_execution_mode_hint:{hint}")

    failures = sorted(set(failures))
    warnings = sorted(set(warnings))
    violations = sorted(set(violations))

    if failures:
        status: CapabilityStatus = "FAIL"
    elif warnings or violations:
        status = "WARNING"
    else:
        status = "OK"

    return {
        "capability_validation_status": status,
        "runtime_model_supported": runtime_model_supported,
        "deployment_profile_supported": deployment_profile_supported,
        "constraint_violations": violations,
        "capability_warnings": warnings,
        "capability_failures": failures,
    }


def _validate_schema_version(raw: Any) -> tuple[CapabilityStatus, list[str]]:
    if raw is None:
        return "FAIL", ["missing_schema_version"]
    if isinstance(raw, bool) or not isinstance(raw, int) or raw <= 0:
        return "FAIL", ["malformed_schema_version"]
    if raw != CAPABILITY_SCHEMA_VERSION:
        return "WARNING", [f"schema_version_mismatch:{raw}"]
    return "OK", []


def build_capability_report(
    output_dir: Path,
    profile: dict[str, Any] | None = None,
    *,
    execution_mode_hint: str | None = None,
) -> dict[str, Any]:
    """Build validation report for capability profile on disk or canonical build."""
    base = output_dir.expanduser().resolve()
    profile_path = default_runtime_capabilities_path(base)
    prof = profile
    profile_present = False
    if prof is None and profile_path.is_file():
        prof = load_runtime_capability_profile(profile_path)
        profile_present = prof is not None
    if prof is None:
        prof = build_runtime_capability_profile(base)
        profile_present = False

    validation = validate_runtime_capabilities(prof, execution_mode_hint=execution_mode_hint)

    report: dict[str, Any] = {
        "schema_version": CAPABILITY_SCHEMA_VERSION,
        "generated_at": _utc_now_iso(),
        "capability_validation_status": validation["capability_validation_status"],
        "profile_present": profile_present,
        "runtime_model_supported": validation["runtime_model_supported"],
        "deployment_profile_supported": validation["deployment_profile_supported"],
        "constraint_violations": validation["constraint_violations"],
        "capability_warnings": validation["capability_warnings"],
        "capability_failures": validation["capability_failures"],
    }
    return {k: report[k] for k in REPORT_KEY_ORDER}


def write_runtime_capability_profile(path: Path, profile: dict[str, Any]) -> Path:
    dest = path.expanduser().resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)
    ordered = {k: profile[k] for k in PROFILE_KEY_ORDER if k in profile}
    payload = json.dumps(ordered, indent=2, sort_keys=True, default=str) + "\n"
    tmp = dest.with_name(dest.name + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, dest)
    return dest


def write_capability_report(path: Path, report: dict[str, Any]) -> Path:
    dest = path.expanduser().resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)
    ordered = {k: report[k] for k in REPORT_KEY_ORDER if k in report}
    payload = json.dumps(ordered, indent=2, sort_keys=True, default=str) + "\n"
    tmp = dest.with_name(dest.name + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, dest)
    return dest


def update_runtime_capabilities(
    output_dir: Path,
    *,
    execution_mode_hint: str | None = None,
) -> tuple[Path, Path]:
    """Write capability profile and validation report (atomic, latest-only)."""
    base = output_dir.expanduser().resolve()
    profile = build_runtime_capability_profile(base, execution_mode_hint=execution_mode_hint)
    prof_path = write_runtime_capability_profile(default_runtime_capabilities_path(base), profile)
    report = build_capability_report(base, profile=profile, execution_mode_hint=execution_mode_hint)
    report_path = write_capability_report(default_capability_report_path(base), report)
    return prof_path, report_path


def strict_capability_exit_code(report: dict[str, Any], *, strict: bool) -> int:
    st = str(report.get("capability_validation_status") or "FAIL")
    if st == "FAIL":
        return 1
    if strict and st != "OK":
        return 1
    return 0


def render_capability_summary(
    profile: dict[str, Any],
    report: dict[str, Any],
) -> str:
    lines = [
        "Runtime capability inspection summary",
        "",
        "Capability profiles describe operational assumptions, not infrastructure automation.",
        "",
        f"Capability validation status: {report.get('capability_validation_status')}",
        f"Profile capability status: {profile.get('capability_status')}",
        f"Runtime model: {profile.get('runtime_model')}",
        f"Deployment profile: {profile.get('deployment_profile')}",
        f"Profile present on disk: {report.get('profile_present')}",
    ]
    chars = profile.get("runtime_characteristics") or {}
    if chars:
        lines.append("")
        lines.append("Runtime characteristics:")
        for k in sorted(chars):
            lines.append(f"  {k}: {chars[k]}")
    for key in ("capability_failures", "capability_warnings", "constraint_violations"):
        items = report.get(key) or []
        if items:
            lines.append(f"{key}: {', '.join(items)}")
    unsupported = profile.get("unsupported_execution_modes") or []
    if unsupported:
        lines.append("")
        lines.append("Explicitly unsupported execution modes:")
        for m in unsupported[:8]:
            lines.append(f"  {m}")
    return "\n".join(lines) + "\n"
