"""Supplemental artifact integrity (opt-in; does not modify frozen runtime JSON)."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

INTEGRITY_REPORT_SCHEMA = 1


def file_sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def build_output_dir_integrity_report(output_dir: Path) -> dict[str, Any]:
    """Checksum catalog for OUTPUT_DIR/runtime/*.json — supplemental to runtime_manifest."""
    base = output_dir.expanduser().resolve()
    rt = base / "runtime"
    files: list[dict[str, Any]] = []
    if rt.is_dir():
        for p in sorted(rt.glob("*.json")):
            files.append(
                {
                    "path": f"runtime/{p.name}",
                    "sha256": file_sha256(p),
                    "size_bytes": p.stat().st_size,
                }
            )
    return {
        "schema_version": INTEGRITY_REPORT_SCHEMA,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "output_dir": str(base),
        "file_count": len(files),
        "files": files,
        "note": "Supplemental integrity catalog; frozen manifest remains authoritative for verify-runtime",
    }


def verify_integrity_report(report: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    base = output_dir.expanduser().resolve()
    mismatches: list[str] = []
    missing: list[str] = []
    for ent in report.get("files") or []:
        if not isinstance(ent, dict):
            continue
        rel = str(ent.get("path") or "")
        expected = ent.get("sha256")
        p = base / rel
        if not p.is_file():
            missing.append(rel)
            continue
        actual = file_sha256(p)
        if expected and actual != expected:
            mismatches.append(rel)
    status = "FAIL" if mismatches or missing else "OK"
    return {
        "integrity_status": status,
        "checksum_mismatches": mismatches,
        "missing_files": missing,
    }


def write_integrity_report(path: Path, report: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path
