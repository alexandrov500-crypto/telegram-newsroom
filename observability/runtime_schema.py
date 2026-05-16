"""Runtime schema registry and inspection-only compatibility validation (stdlib)."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Literal

CompatibilityStatus = Literal["OK", "WARNING", "FAIL"]

CURRENT_RUNTIME_SCHEMA_VERSION = 1
SUPPORTED_SCHEMA_VERSIONS: tuple[int, ...] = (1,)
# Versions newer than max(SUPPORTED) that validators treat as WARNING (forward-compatible).
FUTURE_COMPATIBLE_VERSIONS: frozenset[int] = frozenset({2})

COMPATIBILITY_REPORT_REL = Path("runtime") / "compatibility_report.json"

RUNTIME_ARTIFACT_SPECS: tuple[tuple[str, str, bool], ...] = (
    ("health_snapshot.json", "runtime/health_snapshot.json", True),
    ("runtime_report.json", "runtime/runtime_report.json", True),
    ("runtime_manifest.json", "runtime/runtime_manifest.json", True),
    ("recovery_report.json", "runtime/recovery_report.json", True),
)

COMPATIBILITY_KEY_ORDER: tuple[str, ...] = (
    "artifact_versions",
    "compatibility_failures",
    "compatibility_status",
    "compatibility_warnings",
    "generated_at",
    "runtime_schema_version",
    "supported_versions",
)


def default_compatibility_report_path(base_dir: Path) -> Path:
    return base_dir.expanduser().resolve() / COMPATIBILITY_REPORT_REL


def get_supported_schema_versions() -> list[int]:
    """Explicit supported schema versions (deterministic, sorted)."""
    return sorted(int(v) for v in SUPPORTED_SCHEMA_VERSIONS)


def get_runtime_schema_metadata() -> dict[str, Any]:
    """Deterministic schema metadata for operators and reports."""
    return {
        "current_runtime_schema_version": CURRENT_RUNTIME_SCHEMA_VERSION,
        "evolution_policy": {
            "breaking_changes": [
                "removing required fields",
                "changing field types",
                "changing field semantics",
            ],
            "minor_compatible_changes": [
                "adding optional fields",
                "adding optional artifacts",
            ],
        },
        "future_compatible_versions": sorted(FUTURE_COMPATIBLE_VERSIONS),
        "inspection_only": True,
        "mutates_artifacts": False,
        "supported_versions": get_supported_schema_versions(),
    }


def _parse_schema_version(raw: Any) -> int | None:
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw if raw > 0 else None
    if isinstance(raw, float) and raw.is_integer() and raw > 0:
        return int(raw)
    if isinstance(raw, str) and raw.isdigit():
        v = int(raw)
        return v if v > 0 else None
    return None


def validate_schema_version(
    version: Any,
    *,
    artifact_name: str | None = None,
    required: bool = True,
) -> tuple[CompatibilityStatus, list[str]]:
    """
    Validate a single ``schema_version`` value.
    Returns (status, messages). Does not mutate artifacts.
    """
    label = artifact_name or "artifact"
    if version is None:
        if required:
            return "FAIL", [f"{label}:missing_schema_version"]
        return "WARNING", [f"{label}:missing_optional_schema_version"]

    parsed = _parse_schema_version(version)
    if parsed is None:
        return "FAIL", [f"{label}:malformed_schema_version"]

    supported = get_supported_schema_versions()
    if parsed in supported:
        return "OK", []

    if parsed in FUTURE_COMPATIBLE_VERSIONS:
        return "WARNING", [f"{label}:future_schema_version:{parsed}"]

    return "FAIL", [f"{label}:unsupported_schema_version:{parsed}"]


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _worst_status(a: CompatibilityStatus, b: CompatibilityStatus) -> CompatibilityStatus:
    rank = {"OK": 0, "WARNING": 1, "FAIL": 2}
    return a if rank[a] >= rank[b] else b


def check_runtime_compatibility(output_dir: Path) -> dict[str, Any]:
    """Inspect runtime artifacts and return a compatibility report dict (read-only)."""
    base = output_dir.expanduser().resolve()
    failures: list[str] = []
    warnings: list[str] = []
    artifact_versions: dict[str, int | None] = {}
    overall: CompatibilityStatus = "OK"

    for name, rel, required in RUNTIME_ARTIFACT_SPECS:
        path = base / rel
        doc = _load_json(path)
        if doc is None:
            artifact_versions[name] = None
            if required:
                failures.append(f"missing_artifact:{name}")
                overall = _worst_status(overall, "FAIL")
            else:
                warnings.append(f"missing_optional_artifact:{name}")
                overall = _worst_status(overall, "WARNING")
            continue

        raw_ver = doc.get("schema_version")
        st, msgs = validate_schema_version(
            raw_ver,
            artifact_name=name,
            required=True,
        )
        parsed = _parse_schema_version(raw_ver)
        artifact_versions[name] = parsed

        if st == "FAIL":
            failures.extend(msgs)
            overall = _worst_status(overall, "FAIL")
        elif st == "WARNING":
            warnings.extend(msgs)
            overall = _worst_status(overall, "WARNING")

    # Optional: compatibility_report itself when already on disk
    compat_path = default_compatibility_report_path(base)
    if compat_path.is_file() and "compatibility_report.json" not in artifact_versions:
        doc = _load_json(compat_path)
        if doc is not None:
            st, msgs = validate_schema_version(
                doc.get("schema_version"),
                artifact_name="compatibility_report.json",
                required=False,
            )
            if st == "FAIL":
                failures.extend(msgs)
                overall = _worst_status(overall, "FAIL")
            elif st == "WARNING":
                warnings.extend(msgs)
                overall = _worst_status(overall, "WARNING")

    report: dict[str, Any] = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "compatibility_status": overall,
        "runtime_schema_version": CURRENT_RUNTIME_SCHEMA_VERSION,
        "supported_versions": get_supported_schema_versions(),
        "artifact_versions": {k: artifact_versions[k] for k in sorted(artifact_versions)},
        "compatibility_warnings": sorted(set(warnings)),
        "compatibility_failures": sorted(set(failures)),
        "schema_version": CURRENT_RUNTIME_SCHEMA_VERSION,
    }
    ordered = {k: report[k] for k in COMPATIBILITY_KEY_ORDER if k in report}
    if "schema_version" not in ordered:
        ordered = {"schema_version": report["schema_version"], **ordered}
    return ordered


def build_compatibility_report(output_dir: Path) -> dict[str, Any]:
    """Alias for ``check_runtime_compatibility`` (deterministic inspection)."""
    return check_runtime_compatibility(output_dir)


def write_compatibility_report(path: Path, report: dict[str, Any]) -> Path:
    dest = path.expanduser().resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)
    payload_report = dict(report)
    if "schema_version" not in payload_report:
        payload_report["schema_version"] = CURRENT_RUNTIME_SCHEMA_VERSION
    ordered = {"schema_version": payload_report["schema_version"]}
    for k in COMPATIBILITY_KEY_ORDER:
        if k in payload_report:
            ordered[k] = payload_report[k]
    payload = json.dumps(ordered, indent=2, sort_keys=True, default=str) + "\n"
    tmp = dest.with_name(dest.name + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, dest)
    return dest


def rebuild_compatibility_report(output_dir: Path) -> Path:
    report = build_compatibility_report(output_dir)
    return write_compatibility_report(default_compatibility_report_path(output_dir), report)


def strict_compatibility_exit_code(report: dict[str, Any], *, strict: bool) -> int:
    st = str(report.get("compatibility_status") or "FAIL")
    if st == "FAIL":
        return 1
    if strict and st != "OK":
        return 1
    return 0


def render_compatibility_summary(report: dict[str, Any]) -> str:
    lines = [
        "Runtime compatibility summary",
        "",
        "Compatibility validation is inspection-only and does not mutate artifacts.",
        "",
        f"Compatibility status: {report.get('compatibility_status', 'UNKNOWN')}",
        f"Runtime schema version: {report.get('runtime_schema_version')}",
        f"Supported versions: {report.get('supported_versions')}",
    ]
    versions = report.get("artifact_versions") or {}
    if versions:
        lines.append("")
        lines.append("Artifact schema versions:")
        for name in sorted(versions):
            lines.append(f"  {name}: {versions[name]}")
    for key in ("compatibility_failures", "compatibility_warnings"):
        items = report.get(key) or []
        if items:
            lines.append(f"{key}: {', '.join(items)}")
    status = str(report.get("compatibility_status") or "FAIL")
    if status in ("FAIL", "WARNING"):
        lines.extend(
            [
                "",
                "Operator actions:",
                "  - Run: make check-compatibility OUTPUT_DIR=<dir> --write",
                "  - Fix schema_version on artifacts or re-run nightly",
                "  - Use --strict only after compatibility_status is OK",
            ],
        )
    return "\n".join(lines) + "\n"
