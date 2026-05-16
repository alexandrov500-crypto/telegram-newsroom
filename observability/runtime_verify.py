"""Offline verification of runtime manifests and artifact checksums (stdlib)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from observability.runtime_manifest import (
    OPTIONAL_SPECS,
    REQUIRED_SPECS,
    calculate_file_checksum,
    default_runtime_manifest_path,
    load_runtime_manifest,
)

VerificationStatus = Literal["OK", "WARNING", "FAIL"]

VERIFY_KEY_ORDER: tuple[str, ...] = (
    "checksum_mismatches",
    "missing_optional",
    "missing_required",
    "verification_status",
    "warnings",
)


def verify_required_artifacts(
    base_dir: Path,
    manifest: dict[str, Any] | None,
) -> tuple[list[str], list[str]]:
    """
    Return (missing_required names, warnings for optional gaps).
    Uses manifest artifact list when present; otherwise REQUIRED_SPECS.
    """
    base = base_dir.expanduser().resolve()
    missing_req: list[str] = []
    warnings: list[str] = []

    if manifest and manifest.get("artifacts"):
        for ent in manifest["artifacts"]:
            if not isinstance(ent, dict):
                continue
            name = str(ent.get("name") or "")
            rel = str(ent.get("path") or "")
            required = bool(ent.get("required"))
            present = (base / rel).is_file()
            if required and not present:
                missing_req.append(name or rel)
            elif not required and not present:
                warnings.append(f"missing_optional:{name or rel}")
        for name, rel in REQUIRED_SPECS:
            if not (base / rel).is_file() and name not in missing_req:
                missing_req.append(name)
        for name, rel in OPTIONAL_SPECS:
            if not (base / rel).is_file():
                warnings.append(f"missing_optional:{name}")
        return sorted(missing_req), sorted(warnings)

    for name, rel in REQUIRED_SPECS:
        if not (base / rel).is_file():
            missing_req.append(name)
    for name, rel in OPTIONAL_SPECS:
        if not (base / rel).is_file():
            warnings.append(f"missing_optional:{name}")

    return sorted(missing_req), sorted(warnings)


def verify_artifact_checksums(
    base_dir: Path,
    manifest: dict[str, Any],
) -> tuple[list[str], list[str]]:
    """Return (checksum_mismatches, warnings)."""
    base = base_dir.expanduser().resolve()
    mismatches: list[str] = []
    warnings: list[str] = []

    for ent in manifest.get("artifacts") or []:
        if not isinstance(ent, dict):
            continue
        name = str(ent.get("name") or "")
        rel = str(ent.get("path") or "")
        expected = ent.get("sha256")
        full = base / rel
        if not full.is_file():
            continue
        if expected is None:
            warnings.append(f"no_checksum_in_manifest:{name}")
            continue
        actual = calculate_file_checksum(full)
        if actual is None:
            mismatches.append(f"unreadable:{name}")
        elif actual != str(expected).lower():
            mismatches.append(f"{name}:expected={expected[:12]}… actual={actual[:12]}…")

    bundle = manifest.get("bundle")
    if isinstance(bundle, dict) and bundle.get("exists"):
        rel = str(bundle.get("path") or "runtime_bundle.zip")
        full = base / rel
        expected = bundle.get("sha256")
        if full.is_file() and expected:
            actual = calculate_file_checksum(full)
            if actual and actual != str(expected).lower():
                mismatches.append("runtime_bundle.zip:checksum_mismatch")

    return sorted(mismatches), sorted(warnings)


def verify_runtime_manifest(
    *,
    output_dir: Path,
    manifest_path: Path | None = None,
) -> dict[str, Any]:
    """Full offline verification for an ops output directory."""
    base = output_dir.expanduser().resolve()
    mp = (
        manifest_path.expanduser().resolve()
        if manifest_path
        else default_runtime_manifest_path(base)
    )
    manifest = load_runtime_manifest(mp)

    missing_required: list[str] = []
    missing_optional: list[str] = []
    checksum_mismatches: list[str] = []
    warnings: list[str] = []

    if manifest is None:
        for name, rel in REQUIRED_SPECS:
            if not (base / rel).is_file():
                missing_required.append(name)
        warnings.append("missing:runtime_manifest.json")
        status: VerificationStatus = "FAIL" if missing_required else "WARNING"
        return {
            "checksum_mismatches": [],
            "missing_optional": [],
            "missing_required": sorted(missing_required),
            "verification_status": status,
            "warnings": sorted(warnings),
        }

    missing_required, opt_warns = verify_required_artifacts(base, manifest)
    for w in opt_warns:
        if w.startswith("missing_optional:"):
            missing_optional.append(w.split(":", 1)[-1])
        else:
            warnings.append(w)
    for name, rel in OPTIONAL_SPECS:
        if not (base / rel).is_file() and name not in missing_optional:
            missing_optional.append(name)

    checksum_mismatches, chk_warns = verify_artifact_checksums(base, manifest)
    warnings.extend(chk_warns)

    # Required entries listed in manifest but absent on disk
    for ent in manifest.get("artifacts") or []:
        if isinstance(ent, dict) and ent.get("required"):
            rel = str(ent.get("path") or "")
            name = str(ent.get("name") or rel)
            if rel and not (base / rel).is_file() and name not in missing_required:
                missing_required.append(name)

    missing_required = sorted(set(missing_required))
    missing_optional = sorted(set(missing_optional))
    checksum_mismatches = sorted(set(checksum_mismatches))
    warnings = sorted(set(warnings))

    if missing_required or checksum_mismatches:
        status = "FAIL"
    elif missing_optional or warnings:
        status = "WARNING"
    else:
        status = "OK"

    result = {
        "checksum_mismatches": checksum_mismatches,
        "missing_optional": missing_optional,
        "missing_required": missing_required,
        "verification_status": status,
        "warnings": warnings,
    }
    return {k: result[k] for k in VERIFY_KEY_ORDER}


def strict_verify_exit_code(result: dict[str, Any], *, strict: bool) -> int:
    st = str(result.get("verification_status") or "FAIL")
    if st == "FAIL":
        return 1
    if strict and st != "OK":
        return 1
    return 0


def render_verify_summary(result: dict[str, Any]) -> str:
    lines = [
        "Runtime verification summary",
        "",
        f"Verification status: {result.get('verification_status', 'UNKNOWN')}",
    ]
    for key in ("missing_required", "missing_optional", "checksum_mismatches"):
        items = result.get(key) or []
        if items:
            lines.append(f"{key}: {', '.join(items)}")
    warns = result.get("warnings") or []
    if warns:
        lines.append("")
        lines.append("Warnings:")
        for w in warns[:24]:
            lines.append(f"  {w}")
    status = str(result.get("verification_status") or "FAIL")
    if status in ("FAIL", "WARNING"):
        lines.extend(
            [
                "",
                "Operator actions:",
                "  - Regenerate manifest after nightly: make runtime-manifest OUTPUT_DIR=<dir>",
                "  - Or run full pipeline: make runtime-nightly … then make verify-runtime",
                "  - Do not use examples/runtime_samples/ for checksum verification (demo placeholders)",
            ],
        )
    return "\n".join(lines) + "\n"
