"""Recovery readiness heuristics (read-only; advisory)."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Literal

RecoveryRisk = Literal["LOW", "MEDIUM", "HIGH"]


def estimate_restore_duration_sec(
    *,
    output_dir_bytes: int,
    runtime_artifact_count: int = 12,
    bytes_per_artifact: int = 4096,
) -> float:
    """Copy-only local restore heuristic (explainable; not a SLA)."""
    total_bytes = output_dir_bytes + runtime_artifact_count * bytes_per_artifact
    total_mb = total_bytes / (1024 * 1024)
    return round(max(0.05, total_mb * 0.02 + runtime_artifact_count * 0.05), 4)


def recovery_complexity_score(
    *,
    output_dir_bytes: int,
    wal_bytes: int,
    bundle_present: bool,
    manifest_present: bool,
) -> dict[str, Any]:
    score = 0
    reasons: list[str] = []
    if output_dir_bytes > 500_000_000:
        score += 30
        reasons.append("large OUTPUT_DIR")
    if wal_bytes > 268_435_456:
        score += 25
        reasons.append("large WAL")
    if not bundle_present:
        score += 15
        reasons.append("no runtime_bundle.zip")
    if not manifest_present:
        score += 20
        reasons.append("no runtime_manifest.json")
    level: RecoveryRisk = "LOW"
    if score >= 50:
        level = "HIGH"
    elif score >= 25:
        level = "MEDIUM"
    return {
        "complexity_score": min(100, score),
        "complexity_level": level,
        "reasons": reasons,
    }


def backup_freshness_risk(
    path: Path,
    *,
    warn_hours: float = 48.0,
    critical_hours: float = 168.0,
) -> dict[str, Any]:
    if not path.is_file():
        return {
            "risk": "HIGH",
            "age_hours": None,
            "message": f"backup artifact missing: {path.name}",
        }
    age_h = (time.time() - path.stat().st_mtime) / 3600.0
    if age_h > critical_hours:
        risk: RecoveryRisk = "HIGH"
        msg = f"backup older than {critical_hours}h"
    elif age_h > warn_hours:
        risk = "MEDIUM"
        msg = f"backup older than {warn_hours}h"
    else:
        risk = "LOW"
        msg = "backup within freshness window"
    return {"risk": risk, "age_hours": round(age_h, 2), "message": msg, "path": str(path)}


def detect_unsafe_recovery_patterns(
    *,
    live_db: bool,
    workers_running: bool,
    restore_over_active_db: bool,
) -> list[dict[str, str]]:
    patterns: list[dict[str, str]] = []
    if restore_over_active_db:
        patterns.append(
            {
                "code": "restore_over_active_db",
                "severity": "HIGH",
                "message": "Restore while DB has active writers risks corruption",
            }
        )
    if live_db and workers_running:
        patterns.append(
            {
                "code": "live_restore_with_workers",
                "severity": "HIGH",
                "message": "Quiesce workers before file-level restore",
            }
        )
    return patterns


def build_recovery_assessment(output_dir: Path) -> dict[str, Any]:
    od = output_dir.expanduser().resolve()
    rt = od / "runtime"
    manifest = rt / "runtime_manifest.json"
    bundle = rt / "runtime_bundle.zip"
    total = 0
    if od.is_dir():
        for p in od.rglob("*"):
            if p.is_file():
                try:
                    total += p.stat().st_size
                except OSError:
                    pass
    artifact_count = len(list(rt.glob("*.json"))) if rt.is_dir() else 0
    restore_sec = estimate_restore_duration_sec(
        output_dir_bytes=total,
        runtime_artifact_count=max(artifact_count, 12),
    )
    complexity = recovery_complexity_score(
        output_dir_bytes=total,
        wal_bytes=0,
        bundle_present=bundle.is_file(),
        manifest_present=manifest.is_file(),
    )
    freshness = backup_freshness_risk(bundle if bundle.is_file() else manifest)
    warnings: list[str] = []
    if complexity["complexity_level"] != "LOW":
        warnings.append(f"Recovery complexity {complexity['complexity_level']}")
    if freshness["risk"] != "LOW":
        warnings.append(str(freshness["message"]))
    return {
        "schema_version": 1,
        "read_only": True,
        "output_dir": str(od),
        "restore_duration_estimate_sec": restore_sec,
        "complexity": complexity,
        "backup_freshness": freshness,
        "degraded_recovery_warnings": warnings,
        "unsafe_patterns": detect_unsafe_recovery_patterns(
            live_db=False,
            workers_running=False,
            restore_over_active_db=False,
        ),
    }
