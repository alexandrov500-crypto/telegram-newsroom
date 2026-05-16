"""Immutable archival bundle (stewardship preservation). Read-only."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from utils.freeze_integrity import build_freeze_integrity_report, integrity_report_markdown, write_json_deterministic
from utils.ops_schema_governance import sha256_file
from utils.ops_schema_governance import build_schema_validation_report, validation_report_markdown
from utils.ops_tooling import frozen_utc_now
from utils.repository_fingerprint import build_repository_fingerprint, fingerprint_markdown

IMMUTABLE_ARCHIVE_SCHEMA_VERSION = 1
MAX_IMMUTABLE_ARCHIVE_BYTES = 10 * 1024 * 1024

ARCHIVE_DOC_PATHS = (
    "docs/releases/v3_2_final_manifest.md",
    "docs/releases/v3_2_immutable_baseline.md",
    "docs/releases/v3_2_freeze_validation.md",
    "docs/releases/immutable_repository_certification.md",
    "docs/releases/stewardship_preservation_declaration.md",
    "docs/releases/stewardship_state_declaration.md",
    "docs/releases/offline_recovery_certification.md",
    "docs/governance/governance_preservation_audit.md",
    "docs/architecture/ADR-036-immutable-stewardship-certification.md",
    "docs/architecture/ADR-034-v3-2-finalization-and-stewardship.md",
)


def default_immutable_archive_root(repo_root: Path | None = None) -> Path:
    root = repo_root or Path(__file__).resolve().parents[1]
    return root / "var" / "immutable_archive"


def archive_day_stamp() -> str:
    return frozen_utc_now()[:10].replace("-", "")


def build_immutable_archive_bundle(
    *,
    repo_root: Path,
    history_dir: Path,
    reports_dir: Path,
    archive_dir: Path,
    archive_root: Path,
) -> dict[str, Any]:
    day = archive_day_stamp()
    out = archive_root / day
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

    fp = build_repository_fingerprint(repo_root)
    write_json_deterministic(out / "repository_fingerprint.json", fp)
    (out / "repository_fingerprint.md").write_text(fingerprint_markdown(fp), encoding="utf-8")

    gov_dir = out / "governance"
    gov_dir.mkdir()
    for rel in ARCHIVE_DOC_PATHS:
        src = repo_root / rel
        if src.is_file() and src.stat().st_size < 200_000:
            dest = gov_dir / rel.replace("/", "__")
            shutil.copy2(src, dest)

    proofs = {
        "generated_at": frozen_utc_now(),
        "freeze_integrity_status": freeze.get("status"),
        "schema_validation_status": validation.get("status"),
        "fingerprint_sha256": fp.get("content_sha256"),
        "stewardship_validate": "make stewardship-validate",
        "immutable_baseline_validate": "make immutable-baseline-validate",
    }
    write_json_deterministic(out / "reproducibility_proofs.json", proofs)

    manifest_files: list[dict[str, str]] = []
    total = 0
    for path in sorted(out.rglob("*")):
        if not path.is_file() or path.name in ("manifest.json", "checksums.sha256"):
            continue
        rel = str(path.relative_to(out)).replace("\\", "/")
        size = path.stat().st_size
        total += size
        manifest_files.append({"path": rel, "sha256": sha256_file(path), "bytes": str(size)})

    if total > MAX_IMMUTABLE_ARCHIVE_BYTES:
        raise ValueError(f"immutable archive exceeds cap: {total} > {MAX_IMMUTABLE_ARCHIVE_BYTES}")

    manifest: dict[str, Any] = {
        "schema_version": IMMUTABLE_ARCHIVE_SCHEMA_VERSION,
        "read_only": True,
        "archive_day": day,
        "generated_at": frozen_utc_now(),
        "total_bytes": total,
        "files": manifest_files,
    }
    write_json_deterministic(out / "manifest.json", manifest)
    lines = [f"{e['sha256']}  {e['path']}" for e in manifest_files]
    (out / "checksums.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")

    return {
        "archive_dir": str(out),
        "freeze_status": freeze.get("status"),
        "schema_status": validation.get("status"),
        "manifest": manifest,
    }
