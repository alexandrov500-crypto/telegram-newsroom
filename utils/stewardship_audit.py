"""Stewardship audit bundle assembly (post-freeze). Read-only."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from utils.freeze_integrity import (
    build_freeze_integrity_report,
    integrity_report_markdown,
    write_json_deterministic,
)
from utils.ops_schema_governance import build_schema_validation_report, validation_report_markdown
from utils.ops_tooling import frozen_utc_now

STEWARDSHIP_AUDIT_SCHEMA_VERSION = 1
MAX_STEWARDSHIP_AUDIT_BYTES = 5 * 1024 * 1024

GOVERNANCE_DOC_REFS = (
    "docs/releases/v3_2_freeze_validation.md",
    "docs/releases/v3_2_immutable_baseline.md",
    "docs/releases/offline_recovery_certification.md",
    "docs/releases/stewardship_state_declaration.md",
    "docs/governance/drift_detection_policy.md",
    "docs/governance/stewardship_operations_calendar.md",
    "docs/runbooks/maintenance_hotfix_procedure.md",
)


def default_stewardship_audit_root(repo_root: Path | None = None) -> Path:
    root = repo_root or Path(__file__).resolve().parents[1]
    return root / "var" / "stewardship_audit"


def audit_day_stamp() -> str:
    return frozen_utc_now()[:10].replace("-", "")


def build_stewardship_audit_bundle(
    *,
    repo_root: Path,
    history_dir: Path,
    reports_dir: Path,
    archive_dir: Path,
    audit_root: Path,
) -> dict[str, Any]:
    day = audit_day_stamp()
    out = audit_root / day
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    freeze = build_freeze_integrity_report(repo_root)
    write_json_deterministic(out / "freeze_integrity_report.json", freeze)
    (out / "freeze_integrity_report.md").write_text(integrity_report_markdown(freeze), encoding="utf-8")

    validation = build_schema_validation_report(
        history_dir=history_dir,
        reports_dir=reports_dir,
        archive_dir=archive_dir,
    )
    write_json_deterministic(out / "schema_validation_report.json", validation)
    (out / "schema_validation_report.md").write_text(validation_report_markdown(validation), encoding="utf-8")

    refs: list[dict[str, str]] = []
    for rel in GOVERNANCE_DOC_REFS:
        src = repo_root / rel
        row: dict[str, str] = {"path": rel, "present": str(src.is_file())}
        if src.is_file() and src.stat().st_size < 120_000:
            dest = out / "governance" / rel.replace("/", "_")
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            row["bundled"] = str(dest.relative_to(out)).replace("\\", "/")
        refs.append(row)

    validation_summary = {
        "stewardship_validate": "make stewardship-validate",
        "stewardship_audit_validate": "make stewardship-audit-validate",
        "freeze_tag": freeze.get("freeze_tag"),
        "freeze_integrity_status": freeze.get("status"),
        "schema_validation_status": validation.get("status"),
        "generated_at": frozen_utc_now(),
    }
    write_json_deterministic(out / "validation_summary.json", validation_summary)

    manifest_files: list[dict[str, str]] = []
    total = 0
    for path in sorted(out.rglob("*")):
        if not path.is_file() or path.name in ("manifest.json", "checksums.sha256"):
            continue
        rel = str(path.relative_to(out)).replace("\\", "/")
        size = path.stat().st_size
        total += size
        manifest_files.append({"path": rel, "bytes": str(size)})

    if total > MAX_STEWARDSHIP_AUDIT_BYTES:
        raise ValueError(f"audit bundle exceeds cap: {total} > {MAX_STEWARDSHIP_AUDIT_BYTES}")

    manifest: dict[str, Any] = {
        "schema_version": STEWARDSHIP_AUDIT_SCHEMA_VERSION,
        "read_only": True,
        "audit_day": day,
        "generated_at": frozen_utc_now(),
        "total_bytes": total,
        "governance_refs": refs,
        "files": manifest_files,
    }
    write_json_deterministic(out / "manifest.json", manifest)
    lines = [f"{e['path']}" for e in manifest_files]
    (out / "checksums.sha256").write_text("\n".join(sorted(lines)) + "\n", encoding="utf-8")

    return {
        "audit_dir": str(out),
        "freeze_integrity_status": freeze.get("status"),
        "schema_status": validation.get("status"),
        "manifest": manifest,
    }
