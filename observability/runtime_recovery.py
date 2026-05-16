"""Offline recovery validation and inspection-only replay (stdlib, no mutation)."""

from __future__ import annotations

import json
import os
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any, Literal

from observability.runtime_manifest import (
    default_runtime_manifest_path,
    load_runtime_manifest,
)
from observability.runtime_schema import CURRENT_RUNTIME_SCHEMA_VERSION
from observability.runtime_verify import verify_runtime_manifest
from utils.runtime_bundle import BUNDLE_DIR_NAME

RecoveryStatus = Literal["OK", "WARNING", "FAIL"]

RUNTIME_RECOVERY_REL = Path("runtime") / "recovery_report.json"

STRUCTURE_REQUIRED: tuple[str, ...] = (
    "runtime/health_snapshot.json",
    "runtime/runtime_report.json",
    "runtime/runtime_manifest.json",
)

STRUCTURE_OPTIONAL: tuple[str, ...] = (
    "qualification.json",
    "runtime_bundle.zip",
    "ops_benchmark.json",
)

RECOVERY_REPORT_SCHEMA_VERSION = CURRENT_RUNTIME_SCHEMA_VERSION

RECOVERY_KEY_ORDER: tuple[str, ...] = (
    "schema_version",
    "bundle_extractable",
    "generated_at",
    "recovery_failures",
    "recovery_status",
    "recovery_warnings",
    "required_artifacts_present",
    "runtime_manifest_present",
    "runtime_structure_valid",
    "validated_paths",
    "verification_status",
)


def default_recovery_report_path(base_dir: Path) -> Path:
    return base_dir.expanduser().resolve() / RUNTIME_RECOVERY_REL


def _utc_now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _json_readable(path: Path) -> bool:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return False
    return isinstance(data, (dict, list))


def validate_runtime_structure(output_dir: Path) -> dict[str, Any]:
    """Validate ``runtime/`` layout and JSON readability (read-only)."""
    base = output_dir.expanduser().resolve()
    failures: list[str] = []
    warnings: list[str] = []
    validated: list[str] = []

    rt = base / "runtime"
    if not rt.is_dir():
        failures.append("missing:runtime/")
        return {
            "runtime_structure_valid": False,
            "required_artifacts_present": False,
            "recovery_failures": sorted(failures),
            "recovery_warnings": sorted(warnings),
            "validated_paths": [],
        }

    required_ok = True
    for rel in STRUCTURE_REQUIRED:
        full = base / rel
        if not full.is_file():
            failures.append(f"missing:{rel}")
            required_ok = False
            continue
        if rel.endswith(".json") and not _json_readable(full):
            failures.append(f"invalid_json:{rel}")
            required_ok = False
            continue
        validated.append(rel.replace("\\", "/"))

    for rel in STRUCTURE_OPTIONAL:
        full = base / rel
        if full.is_file():
            if rel.endswith(".json") and not _json_readable(full):
                warnings.append(f"invalid_json:{rel}")
            else:
                validated.append(rel.replace("\\", "/"))
        else:
            warnings.append(f"missing_optional:{rel}")

    return {
        "runtime_structure_valid": required_ok and not failures,
        "required_artifacts_present": required_ok,
        "recovery_failures": sorted(failures),
        "recovery_warnings": sorted(warnings),
        "validated_paths": sorted(validated),
    }


def validate_runtime_bundle(
    output_dir: Path,
    *,
    extract_dir: Path | None = None,
) -> dict[str, Any]:
    """
    Test zip extractability into ``extract_dir`` (or a private temp dir).
    Does not modify ``output_dir``.
    """
    base = output_dir.expanduser().resolve()
    zip_path = base / "runtime_bundle.zip"
    failures: list[str] = []
    warnings: list[str] = []

    if not zip_path.is_file():
        return {
            "bundle_extractable": False,
            "recovery_failures": [],
            "recovery_warnings": ["missing_optional:runtime_bundle.zip"],
        }

    owned_temp: tempfile.TemporaryDirectory[str] | None = None
    target = extract_dir
    if target is None:
        owned_temp = tempfile.TemporaryDirectory(prefix="newsroom_recovery_")
        target = Path(owned_temp.name)

    extractable = False
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            bad = zf.testzip()
            if bad is not None:
                failures.append(f"bundle_corrupt:{bad}")
            else:
                zf.extractall(target)
                names = zf.namelist()
                prefix = f"{BUNDLE_DIR_NAME}/"
                inner = [n for n in names if n.startswith(prefix) and not n.endswith("/")]
                if not inner:
                    failures.append("bundle_empty:runtime_bundle")
                elif f"{prefix}manifest.json" not in names:
                    warnings.append("bundle_missing:runtime_bundle/manifest.json")
                extractable = not failures
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        failures.append(f"bundle_unreadable:{exc!r}")

    if owned_temp is not None:
        owned_temp.cleanup()

    return {
        "bundle_extractable": extractable,
        "recovery_failures": sorted(failures),
        "recovery_warnings": sorted(warnings),
    }


def build_recovery_report(
    *,
    output_dir: Path,
    structure: dict[str, Any],
    bundle: dict[str, Any],
    verification: dict[str, Any],
) -> dict[str, Any]:
    """Assemble deterministic recovery report dict."""
    base = output_dir.expanduser().resolve()
    manifest_present = load_runtime_manifest(default_runtime_manifest_path(base)) is not None

    failures: list[str] = []
    warnings: list[str] = []

    for block in (structure, bundle):
        failures.extend(block.get("recovery_failures") or [])
        warnings.extend(block.get("recovery_warnings") or [])

    failures.extend(verification.get("missing_required") or [])
    failures.extend(verification.get("checksum_mismatches") or [])
    for w in verification.get("warnings") or []:
        warnings.append(str(w))
    for name in verification.get("missing_optional") or []:
        warnings.append(f"missing_optional:{name}")

    if not structure.get("runtime_structure_valid"):
        if not failures:
            failures.append("runtime_structure_invalid")
    if not structure.get("required_artifacts_present"):
        if "required_artifacts_missing" not in failures:
            failures.append("required_artifacts_missing")

    ver_st = str(verification.get("verification_status") or "FAIL")
    if ver_st == "FAIL":
        failures.append("verification_fail")
    elif ver_st == "WARNING" and not manifest_present:
        warnings.append("missing:runtime_manifest.json")

    bundle_extractable = bool(bundle.get("bundle_extractable"))
    zip_present = (base / "runtime_bundle.zip").is_file()
    if zip_present and not bundle_extractable:
        if not any(f.startswith("bundle_") for f in failures):
            failures.append("bundle_not_extractable")

    failures = sorted(set(failures))
    warnings = sorted(set(warnings))

    if failures:
        recovery_status: RecoveryStatus = "FAIL"
    elif warnings or ver_st == "WARNING":
        recovery_status = "WARNING"
    else:
        recovery_status = "OK"

    validated_paths = sorted(
        set(structure.get("validated_paths") or [])
        | {p for p in STRUCTURE_REQUIRED if (base / p).is_file()}
    )

    report: dict[str, Any] = {
        "schema_version": RECOVERY_REPORT_SCHEMA_VERSION,
        "generated_at": _utc_now_iso(),
        "recovery_status": recovery_status,
        "runtime_manifest_present": manifest_present,
        "verification_status": ver_st,
        "bundle_extractable": bundle_extractable if zip_present else False,
        "required_artifacts_present": bool(structure.get("required_artifacts_present")),
        "runtime_structure_valid": bool(structure.get("runtime_structure_valid")),
        "recovery_warnings": warnings,
        "recovery_failures": failures,
        "validated_paths": validated_paths,
    }
    return {k: report[k] for k in RECOVERY_KEY_ORDER}


def validate_runtime_recovery(
    output_dir: Path,
    *,
    extract_bundle: bool = True,
) -> dict[str, Any]:
    """Full offline recovery validation (read-only on ``output_dir``)."""
    base = output_dir.expanduser().resolve()
    structure = validate_runtime_structure(base)
    verification = verify_runtime_manifest(output_dir=base)

    bundle: dict[str, Any]
    if extract_bundle and (base / "runtime_bundle.zip").is_file():
        with tempfile.TemporaryDirectory(prefix="newsroom_recovery_") as td:
            bundle = validate_runtime_bundle(base, extract_dir=Path(td))
    else:
        bundle = validate_runtime_bundle(base, extract_dir=None)

    return build_recovery_report(
        output_dir=base,
        structure=structure,
        bundle=bundle,
        verification=verification,
    )


def write_recovery_report(path: Path, report: dict[str, Any]) -> Path:
    dest = path.expanduser().resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)
    ordered = {k: report[k] for k in RECOVERY_KEY_ORDER if k in report}
    payload = json.dumps(ordered, indent=2, sort_keys=True, default=str) + "\n"
    tmp = dest.with_name(dest.name + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, dest)
    return dest


def rebuild_recovery_report(output_dir: Path) -> Path:
    report = validate_runtime_recovery(output_dir)
    return write_recovery_report(default_recovery_report_path(output_dir), report)


def strict_recovery_exit_code(report: dict[str, Any], *, strict: bool) -> int:
    st = str(report.get("recovery_status") or "FAIL")
    if st == "FAIL":
        return 1
    if strict and st != "OK":
        return 1
    return 0


def render_recovery_summary(report: dict[str, Any]) -> str:
    lines = [
        "Runtime recovery validation summary",
        "",
        f"Recovery status: {report.get('recovery_status', 'UNKNOWN')}",
        f"Verification status: {report.get('verification_status', 'UNKNOWN')}",
        f"Runtime structure valid: {report.get('runtime_structure_valid')}",
        f"Bundle extractable: {report.get('bundle_extractable')}",
        f"Manifest present: {report.get('runtime_manifest_present')}",
    ]
    for key in ("recovery_failures", "recovery_warnings"):
        items = report.get(key) or []
        if items:
            lines.append(f"{key}: {', '.join(items)}")
    paths = report.get("validated_paths") or []
    if paths:
        lines.append("")
        lines.append("Validated paths:")
        for p in paths[:16]:
            lines.append(f"  {p}")
    return "\n".join(lines) + "\n"


def replay_runtime_inspection(output_dir: Path) -> dict[str, Any]:
    """
    Inspection-only replay: extract bundle to temp, verify, validate structure.
    Removes temp directory before return. Does not execute pipelines.
    """
    base = output_dir.expanduser().resolve()
    zip_path = base / "runtime_bundle.zip"
    bundle_inner_valid = False
    extracted = False

    if zip_path.is_file():
        with tempfile.TemporaryDirectory(prefix="newsroom_replay_") as td:
            extracted = True
            extract_root = Path(td)
            bundle = validate_runtime_bundle(base, extract_dir=extract_root)
            bundle_inner_valid = (extract_root / BUNDLE_DIR_NAME / "manifest.json").is_file()
            if not bundle_inner_valid and bundle.get("bundle_extractable"):
                bundle = {
                    **bundle,
                    "recovery_warnings": sorted(
                        set(bundle.get("recovery_warnings") or [])
                        | {"replay:inner_manifest_missing"},
                    ),
                }
            structure = validate_runtime_structure(base)
            verification = verify_runtime_manifest(output_dir=base)
            report = build_recovery_report(
                output_dir=base,
                structure=structure,
                bundle=bundle,
                verification=verification,
            )
    else:
        bundle = validate_runtime_bundle(base, extract_dir=None)
        structure = validate_runtime_structure(base)
        verification = verify_runtime_manifest(output_dir=base)
        report = build_recovery_report(
            output_dir=base,
            structure=structure,
            bundle=bundle,
            verification=verification,
        )

    report = dict(report)
    report["replay"] = {
        "bundle_inner_manifest_valid": bundle_inner_valid,
        "extracted_to_temp": extracted,
        "inspection_only": True,
        "pipeline_executed": False,
    }
    return report


def render_replay_summary(result: dict[str, Any]) -> str:
    lines = [
        "Runtime replay inspection summary",
        "",
        "Replay workflows are inspection-only and do not re-execute newsroom pipelines.",
        "",
        f"Recovery status: {result.get('recovery_status', 'UNKNOWN')}",
        f"Verification status: {result.get('verification_status', 'UNKNOWN')}",
    ]
    replay = result.get("replay") or {}
    if replay.get("extracted_to_temp"):
        lines.append("Bundle extracted to temporary directory (removed after inspection).")
    lines.append(f"Inner bundle manifest valid: {replay.get('bundle_inner_manifest_valid')}")
    lines.append(f"Pipeline executed: {replay.get('pipeline_executed')}")
    for key in ("recovery_failures", "recovery_warnings"):
        items = result.get(key) or []
        if items:
            lines.append(f"{key}: {', '.join(items)}")
    return "\n".join(lines) + "\n"
