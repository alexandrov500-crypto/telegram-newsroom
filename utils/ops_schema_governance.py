"""Operational schema governance and validation (v3.2 P3). Read-only."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from utils.ops_analytics import ANALYTICS_SCHEMA_VERSION, default_archive_dir, verify_archive_file
from utils.ops_tooling import (
    OPS_SNAPSHOT_SCHEMA_VERSION,
    frozen_utc_now,
    list_snapshots,
    validate_snapshot_document,
)

DIAGNOSTICS_SCHEMA_VERSION = 2
VALIDATION_REPORT_SCHEMA_VERSION = 1
MAX_BUNDLE_BYTES = 30 * 1024 * 1024

REQUIRED_SNAPSHOT_FIELDS = (
    "schema_version",
    "snapshot_kind",
    "read_only",
    "no_telegram_api_calls",
    "no_redis_mutations",
    "captured_at",
    "diagnostics",
)

REQUIRED_ANALYTICS_EXPORT_FIELDS = (
    "schema_version",
    "analytics_kind",
    "read_only",
    "offline",
    "generated_at",
    "snapshot_count",
    "trends",
)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def validate_snapshot_file(path: Path) -> dict[str, Any]:
    row: dict[str, Any] = {"path": path.name, "kind": "snapshot"}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("not_object")
        issues = validate_snapshot_document(data)
        if issues:
            row["status"] = "FAIL"
            row["issues"] = issues
            return row
        diag = data.get("diagnostics") or {}
        dsv = diag.get("schema_version")
        if dsv is not None and int(dsv) != DIAGNOSTICS_SCHEMA_VERSION:
            row["status"] = "WARN"
            row["issues"] = [f"diagnostics_schema_expected_{DIAGNOSTICS_SCHEMA_VERSION}"]
            return row
        row["status"] = "OK"
        return row
    except (json.JSONDecodeError, OSError, ValueError) as exc:
        row["status"] = "CORRUPT"
        row["error"] = repr(exc)
        return row


def validate_analytics_file(path: Path) -> dict[str, Any]:
    row: dict[str, Any] = {"path": path.name, "kind": "analytics"}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("not_object")
        if int(data.get("schema_version", 0)) != ANALYTICS_SCHEMA_VERSION:
            row["status"] = "FAIL"
            row["issues"] = ["analytics_schema_version_mismatch"]
            return row
        missing = [k for k in REQUIRED_ANALYTICS_EXPORT_FIELDS if k not in data]
        if missing:
            row["status"] = "FAIL"
            row["issues"] = [f"missing:{','.join(missing)}"]
            return row
        row["status"] = "OK"
        return row
    except (json.JSONDecodeError, OSError) as exc:
        row["status"] = "CORRUPT"
        row["error"] = repr(exc)
        return row


def validate_archives(archive_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not archive_dir.is_dir():
        return rows
    for path in sorted(archive_dir.rglob("*.json.gz")):
        ok = verify_archive_file(path)
        rows.append(
            {
                "path": str(path.relative_to(archive_dir)),
                "kind": "archive",
                "status": "OK" if ok else "CORRUPT",
            }
        )
    return rows


def build_schema_validation_report(
    *,
    history_dir: Path,
    reports_dir: Path,
    archive_dir: Path,
) -> dict[str, Any]:
    snapshot_rows: list[dict[str, Any]] = []
    if history_dir.is_dir():
        paths = sorted(history_dir.glob("*.json"))
    else:
        paths = []
    for path in paths:
        snapshot_rows.append(validate_snapshot_file(path))

    analytics_rows: list[dict[str, Any]] = []
    if reports_dir.is_dir():
        for path in sorted(reports_dir.glob("analytics_summary.json")):
            analytics_rows.append(validate_analytics_file(path))

    archive_rows = validate_archives(archive_dir)

    all_rows = snapshot_rows + analytics_rows + archive_rows
    corrupt = sum(1 for r in all_rows if r.get("status") == "CORRUPT")
    fail = sum(1 for r in all_rows if r.get("status") == "FAIL")
    warn = sum(1 for r in all_rows if r.get("status") == "WARN")

    status = "FAIL" if fail or corrupt else ("WARNING" if warn else "OK")

    drift: list[str] = []
    for r in snapshot_rows:
        if r.get("status") == "FAIL" and "schema_version" in str(r.get("issues")):
            drift.append(f"snapshot:{r.get('path')}")

    return {
        "schema_version": VALIDATION_REPORT_SCHEMA_VERSION,
        "read_only": True,
        "offline": True,
        "generated_at": frozen_utc_now(),
        "status": status,
        "governance": {
            "snapshot_schema_version": OPS_SNAPSHOT_SCHEMA_VERSION,
            "diagnostics_schema_version": DIAGNOSTICS_SCHEMA_VERSION,
            "analytics_schema_version": ANALYTICS_SCHEMA_VERSION,
        },
        "counts": {
            "snapshots": len(snapshot_rows),
            "corrupt": corrupt,
            "fail": fail,
            "warn": warn,
        },
        "schema_drift": drift,
        "snapshots": snapshot_rows,
        "analytics": analytics_rows,
        "archives": archive_rows,
    }


def validation_report_markdown(report: dict[str, Any]) -> str:
    c = report.get("counts") or {}
    lines = [
        "# Ops schema validation report",
        "",
        f"Generated: {report.get('generated_at')}",
        f"Status: **{report.get('status')}**",
        "",
        "## Governance versions",
        "",
        f"- Snapshot wrapper: {report.get('governance', {}).get('snapshot_schema_version')}",
        f"- Diagnostics embed: {report.get('governance', {}).get('diagnostics_schema_version')}",
        f"- Analytics export: {report.get('governance', {}).get('analytics_schema_version')}",
        "",
        "## Summary",
        "",
        f"- Snapshots checked: {c.get('snapshots')}",
        f"- Corrupt: {c.get('corrupt')}",
        f"- Fail: {c.get('fail')}",
        f"- Warn: {c.get('warn')}",
        "",
    ]
    drift = report.get("schema_drift") or []
    if drift:
        lines.append("## Schema drift\n")
        for d in drift:
            lines.append(f"- {d}")
        lines.append("")
    return "\n".join(lines)


def write_json_deterministic(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
