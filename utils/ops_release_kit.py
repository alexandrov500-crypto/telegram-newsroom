"""Offline operational release kit assembly (v3.2 P4). Read-only."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from utils.ops_analytics import ANALYTICS_SCHEMA_VERSION, default_archive_dir, default_reports_dir
from utils.ops_bundle import build_ops_html_report, export_ops_bundle
from utils.ops_schema_governance import (
    DIAGNOSTICS_SCHEMA_VERSION,
    MAX_BUNDLE_BYTES,
    sha256_file,
    write_json_deterministic,
)
from utils.ops_tooling import (
    DEFAULT_MAX_SNAPSHOT_FILES,
    DEFAULT_MAX_TOTAL_BYTES,
    OPS_SNAPSHOT_SCHEMA_VERSION,
    default_history_dir,
    frozen_utc_now,
    list_snapshots,
)

OPS_TOOLING_RELEASE_VERSION = "v3.2-ops-tooling-1"
RELEASE_KIT_SCHEMA_VERSION = 1
MAX_RELEASE_KIT_BYTES = MAX_BUNDLE_BYTES


def default_release_kit_root(repo_root: Path | None = None) -> Path:
    root = repo_root or Path(__file__).resolve().parents[1]
    return root / "var" / "ops_release_kit"


def build_retention_status(
    history_dir: Path,
    archive_dir: Path,
) -> dict[str, Any]:
    snapshots = list_snapshots(history_dir)
    total_bytes = sum(p.stat().st_size for p in snapshots) if snapshots else 0
    archive_files = list(archive_dir.rglob("*.json.gz")) if archive_dir.is_dir() else []
    archive_bytes = sum(p.stat().st_size for p in archive_files)
    return {
        "schema_version": 1,
        "read_only": True,
        "generated_at": frozen_utc_now(),
        "active_snapshots": {
            "count": len(snapshots),
            "total_bytes": total_bytes,
            "max_files": DEFAULT_MAX_SNAPSHOT_FILES,
            "max_total_bytes": DEFAULT_MAX_TOTAL_BYTES,
        },
        "archive": {
            "file_count": len(archive_files),
            "total_bytes": archive_bytes,
        },
        "policy_doc": "docs/operations/metrics_retention_policy.md",
    }


def _release_readme(stamp: str) -> str:
    return f"""Operational release kit
========================
Version: {OPS_TOOLING_RELEASE_VERSION}
Generated: {frozen_utc_now()}
Stamp: {stamp}

Contents:
- operations_report.html  (offline single-file report)
- analytics_summary.json / .md
- *.svg                 (static charts)
- validation_report.json / .md
- shift_handoff.md
- retention_status.json
- manifest.json + checksums.sha256

Usage (offline):
1. Verify: sha256sum -c checksums.sha256
2. Open operations_report.html in a browser (no network required)
3. Review shift_handoff.md before shift change

Recovery: see docs/runbooks/offline_ops_recovery_drill.md
No Telegram, Redis, or runtime services required.
"""


def _finalize_kit_manifest(out: Path, stamp: str) -> dict[str, Any]:
    manifest_files: list[dict[str, str]] = []
    total = 0
    skip = {"manifest.json", "checksums.sha256"}
    for path in sorted(out.rglob("*")):
        if not path.is_file() or path.name in skip:
            continue
        rel = str(path.relative_to(out)).replace("\\", "/")
        size = path.stat().st_size
        total += size
        manifest_files.append({"path": rel, "sha256": sha256_file(path), "bytes": str(size)})
    if total > MAX_RELEASE_KIT_BYTES:
        raise ValueError(f"release kit exceeds max size: {total} > {MAX_RELEASE_KIT_BYTES}")
    manifest: dict[str, Any] = {
        "schema_version": RELEASE_KIT_SCHEMA_VERSION,
        "read_only": True,
        "kit_kind": "ops_release_kit",
        "tooling_version": OPS_TOOLING_RELEASE_VERSION,
        "generated_at": frozen_utc_now(),
        "kit_stamp": stamp,
        "total_bytes": total,
        "files": manifest_files,
    }
    write_json_deterministic(out / "manifest.json", manifest)
    lines = [f"{e['sha256']}  {e['path']}" for e in manifest_files]
    (out / "checksums.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return manifest


def build_ops_release_kit(
    *,
    history_dir: Path,
    reports_dir: Path,
    archive_dir: Path,
    kit_root: Path,
    limit: int = 200,
) -> dict[str, Any]:
    stamp = frozen_utc_now().replace(":", "")
    out = kit_root / stamp
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    staging = kit_root / f".staging_{stamp}"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    try:
        bundle_result = export_ops_bundle(
            history_dir=history_dir,
            reports_dir=reports_dir,
            archive_dir=archive_dir,
            bundle_root=staging,
            limit=limit,
        )
        bundle_dir = Path(bundle_result["bundle_dir"])
        for item in sorted(bundle_dir.iterdir()):
            dest = out / item.name
            if item.is_dir():
                shutil.copytree(item, dest)
            else:
                shutil.copy2(item, dest)

        write_json_deterministic(out / "retention_status.json", build_retention_status(history_dir, archive_dir))
        (out / "VERSION").write_text(OPS_TOOLING_RELEASE_VERSION + "\n", encoding="utf-8")
        (out / "README.txt").write_text(_release_readme(stamp), encoding="utf-8")

        validation = json.loads((out / "validation_report.json").read_text(encoding="utf-8"))
        html = build_ops_html_report(
            bundle_dir=out,
            validation_report=validation,
            analytics_path=out / "analytics_summary.json",
        )
        (out / "operations_report.html").write_text(html, encoding="utf-8")

        manifest = _finalize_kit_manifest(out, stamp)
    finally:
        if staging.exists():
            shutil.rmtree(staging)

    return {
        "kit_dir": str(out),
        "manifest": manifest,
        "validation_status": bundle_result.get("validation_status"),
        "tooling_version": OPS_TOOLING_RELEASE_VERSION,
    }


def verify_release_kit_checksums(kit_dir: Path) -> tuple[bool, list[str]]:
    errors: list[str] = []
    manifest_path = kit_dir / "manifest.json"
    if not manifest_path.is_file():
        return False, ["missing_manifest"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for entry in manifest.get("files") or []:
        rel = entry.get("path")
        expected = entry.get("sha256")
        if not rel or not expected:
            errors.append("invalid_manifest_entry")
            continue
        path = kit_dir / rel
        if not path.is_file():
            errors.append(f"missing:{rel}")
            continue
        if sha256_file(path) != expected:
            errors.append(f"checksum_mismatch:{rel}")
    return len(errors) == 0, errors


def governance_versions_block() -> dict[str, int]:
    return {
        "snapshot": OPS_SNAPSHOT_SCHEMA_VERSION,
        "diagnostics": DIAGNOSTICS_SCHEMA_VERSION,
        "analytics": ANALYTICS_SCHEMA_VERSION,
        "release_kit": RELEASE_KIT_SCHEMA_VERSION,
    }
