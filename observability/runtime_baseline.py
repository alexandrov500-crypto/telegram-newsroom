"""Deterministic runtime baseline and fixed-threshold drift inspection (stdlib)."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Literal

from observability.health_snapshot import (
    default_health_snapshot_path,
    load_health_snapshot,
    load_health_snapshot_sidecar_json,
)
from observability.runtime_history import (
    default_audit_snapshot_path,
    default_qualification_history_path,
    load_qualification_history,
)
from observability.runtime_report import default_runtime_report_path, load_runtime_report
from observability.runtime_schema import (
    CURRENT_RUNTIME_SCHEMA_VERSION,
    FUTURE_COMPATIBLE_VERSIONS,
    get_supported_schema_versions,
    validate_schema_version,
)

DriftStatus = Literal["OK", "WARNING", "FAIL"]

RUNTIME_BASELINE_REL = Path("runtime") / "runtime_baseline.json"
DRIFT_REPORT_REL = Path("runtime") / "drift_report.json"

RUNTIME_DURATION_WARNING_THRESHOLD_SEC = 15.0

BASELINE_SCHEMA_VERSION = CURRENT_RUNTIME_SCHEMA_VERSION

BASELINE_KEY_ORDER: tuple[str, ...] = (
    "artifact_versions",
    "baseline_status",
    "compatibility_status",
    "generated_at",
    "incident_level",
    "qualification_status",
    "recovery_status",
    "runtime_duration_sec",
    "schema_version",
    "status_summary",
    "verification_status",
)

DRIFT_KEY_ORDER: tuple[str, ...] = (
    "artifact_version_drift",
    "baseline_present",
    "drift_failures",
    "drift_status",
    "drift_warnings",
    "generated_at",
    "incident_level_changed",
    "qualification_changed",
    "runtime_duration_delta_sec",
    "schema_version",
    "status_summary_delta",
)

TRACKED_ARTIFACT_VERSION_KEYS: tuple[str, ...] = (
    "health_snapshot.json",
    "runtime_report.json",
    "runtime_manifest.json",
    "recovery_report.json",
)

_QUAL_RANK = {"OK": 0, "SKIPPED": 0, "NONE": 0, "WARNING": 1, "FAIL": 2, "ERROR": 2}
_INCIDENT_RANK = {"NONE": 0, "OK": 0, "WARNING": 1, "ERROR": 2, "FAIL": 2}


def default_runtime_baseline_path(base_dir: Path) -> Path:
    return base_dir.expanduser().resolve() / RUNTIME_BASELINE_REL


def default_drift_report_path(base_dir: Path) -> Path:
    return base_dir.expanduser().resolve() / DRIFT_REPORT_REL


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


def _status_str(value: Any, default: str = "OK") -> str:
    if value is None:
        return default
    return str(value).upper()


def _rank(value: str, table: dict[str, int]) -> int:
    return table.get(_status_str(value), 1)


def _collect_artifact_versions(base: Path) -> dict[str, int]:
    versions: dict[str, int] = {}
    paths = {
        "health_snapshot.json": base / "runtime" / "health_snapshot.json",
        "runtime_report.json": base / "runtime" / "runtime_report.json",
        "runtime_manifest.json": base / "runtime" / "runtime_manifest.json",
        "recovery_report.json": base / "runtime" / "recovery_report.json",
    }
    compat = _load_json(base / "runtime" / "compatibility_report.json")
    if compat and compat.get("artifact_versions"):
        for name in TRACKED_ARTIFACT_VERSION_KEYS:
            raw = compat["artifact_versions"].get(name)
            if raw is not None:
                try:
                    versions[name] = int(raw)
                except (TypeError, ValueError):
                    pass
    for name, path in paths.items():
        if name in versions:
            continue
        doc = _load_json(path)
        if doc is not None and doc.get("schema_version") is not None:
            try:
                versions[name] = int(doc["schema_version"])
            except (TypeError, ValueError):
                pass
    return {k: versions[k] for k in sorted(versions)}


def _collect_status_summary(base: Path) -> dict[str, int]:
    audit = _load_json(default_audit_snapshot_path(base))
    if audit and isinstance(audit.get("status_summary"), dict):
        return {
            "OK": int(audit["status_summary"].get("OK") or 0),
            "WARNING": int(audit["status_summary"].get("WARNING") or 0),
            "FAIL": int(audit["status_summary"].get("FAIL") or 0),
        }
    hist = load_qualification_history(default_qualification_history_path(base))
    summary = {"OK": 0, "WARNING": 0, "FAIL": 0}
    for entry in hist.get("entries") or []:
        if not isinstance(entry, dict):
            continue
        st = _status_str(entry.get("qualification_status"))
        if st in summary:
            summary[st] += 1
    return summary


def _collect_operational_snapshot(output_dir: Path) -> dict[str, Any]:
    """Lightweight metadata snapshot (no logs/payloads)."""
    base = output_dir.expanduser().resolve()
    qual = load_health_snapshot_sidecar_json(base / "qualification.json")
    rpt = load_runtime_report(default_runtime_report_path(base))
    snap = load_health_snapshot(default_health_snapshot_path(base))
    recovery = _load_json(base / "runtime" / "recovery_report.json")
    compat = _load_json(base / "runtime" / "compatibility_report.json")

    qual_st = "OK"
    if qual:
        qual_st = _status_str(qual.get("qualification_status"))
    elif rpt and rpt.get("qualification_status"):
        qual_st = _status_str(rpt.get("qualification_status"))

    incident = "NONE"
    if rpt:
        incident = str(rpt.get("incident_level") or "NONE").upper()

    duration = 0.0
    if snap is not None:
        duration = round(float(snap.get("runtime_duration_sec") or 0.0), 3)

    missing_required: list[str] = []
    for name in TRACKED_ARTIFACT_VERSION_KEYS:
        rel = {
            "health_snapshot.json": "runtime/health_snapshot.json",
            "runtime_report.json": "runtime/runtime_report.json",
            "runtime_manifest.json": "runtime/runtime_manifest.json",
            "recovery_report.json": "runtime/recovery_report.json",
        }[name]
        if not (base / rel).is_file():
            missing_required.append(name)

    return {
        "qualification_status": qual_st,
        "incident_level": incident,
        "runtime_duration_sec": duration,
        "verification_status": _status_str(
            recovery.get("verification_status") if recovery else "OK",
        ),
        "recovery_status": _status_str(recovery.get("recovery_status") if recovery else "OK"),
        "compatibility_status": _status_str(
            compat.get("compatibility_status") if compat else "OK",
        ),
        "status_summary": _collect_status_summary(base),
        "artifact_versions": _collect_artifact_versions(base),
        "missing_required_artifacts": sorted(missing_required),
    }


def _baseline_status_from_snapshot(snap: dict[str, Any]) -> str:
    if snap.get("missing_required_artifacts"):
        return "FAIL"
    if _status_str(snap.get("qualification_status")) == "FAIL":
        return "FAIL"
    if _status_str(snap.get("incident_level")) in ("ERROR", "FAIL"):
        return "FAIL"
    if any(
        _status_str(snap.get(k)) in ("FAIL", "WARNING")
        for k in ("verification_status", "recovery_status", "compatibility_status")
    ):
        return "WARNING"
    if _status_str(snap.get("incident_level")) == "WARNING":
        return "WARNING"
    return "OK"


def build_runtime_baseline(output_dir: Path) -> dict[str, Any]:
    """Build known-good baseline snapshot from current ops output (inspection-only)."""
    snap = _collect_operational_snapshot(output_dir)
    baseline: dict[str, Any] = {
        "schema_version": BASELINE_SCHEMA_VERSION,
        "generated_at": _utc_now_iso(),
        "baseline_status": _baseline_status_from_snapshot(snap),
        "qualification_status": snap["qualification_status"],
        "incident_level": snap["incident_level"],
        "runtime_duration_sec": snap["runtime_duration_sec"],
        "status_summary": snap["status_summary"],
        "artifact_versions": snap["artifact_versions"],
        "verification_status": snap["verification_status"],
        "recovery_status": snap["recovery_status"],
        "compatibility_status": snap["compatibility_status"],
    }
    return {k: baseline[k] for k in BASELINE_KEY_ORDER}


def load_runtime_baseline(path: Path) -> dict[str, Any] | None:
    data = _load_json(path.expanduser().resolve())
    if data is None:
        return None
    return {k: data[k] for k in BASELINE_KEY_ORDER if k in data}


def write_runtime_baseline(path: Path, baseline: dict[str, Any]) -> Path:
    dest = path.expanduser().resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)
    ordered = {k: baseline[k] for k in BASELINE_KEY_ORDER if k in baseline}
    payload = json.dumps(ordered, indent=2, sort_keys=True, default=str) + "\n"
    tmp = dest.with_name(dest.name + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, dest)
    return dest


def compare_runtime_against_baseline(
    output_dir: Path,
    baseline: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compare current operational snapshot to baseline (read-only on artifacts)."""
    base = output_dir.expanduser().resolve()
    baseline_path = default_runtime_baseline_path(base)
    base_doc = baseline if baseline is not None else load_runtime_baseline(baseline_path)
    current = _collect_operational_snapshot(base)

    failures: list[str] = []
    warnings: list[str] = []

    if base_doc is None:
        missing_msgs: list[str] = []
        fail_msgs: list[str] = []
        if baseline_path.is_file():
            fail_msgs.append("baseline_unreadable")
        else:
            missing_msgs.append("baseline_not_present")
        return {
            "baseline_present": False,
            "current": current,
            "qualification_changed": False,
            "incident_level_changed": False,
            "runtime_duration_delta_sec": 0.0,
            "artifact_version_drift": [],
            "status_summary_delta": {},
            "failures": fail_msgs,
            "warnings": missing_msgs,
        }

    st, msgs = validate_schema_version(
        base_doc.get("schema_version"),
        artifact_name="runtime_baseline.json",
        required=True,
    )
    if st == "FAIL":
        failures.extend(msgs)
    elif st == "WARNING":
        warnings.extend(msgs)

    supported = set(get_supported_schema_versions()) | set(FUTURE_COMPATIBLE_VERSIONS)
    for name, ver in current.get("artifact_versions", {}).items():
        if ver not in supported:
            failures.append(f"incompatible_schema:{name}:{ver}")

    for name in current.get("missing_required_artifacts") or []:
        failures.append(f"missing_required_artifact:{name}")

    qual_changed = _rank(current["qualification_status"], _QUAL_RANK) > _rank(
        base_doc.get("qualification_status"),
        _QUAL_RANK,
    )
    incident_changed = _rank(current["incident_level"], _INCIDENT_RANK) > _rank(
        base_doc.get("incident_level"),
        _INCIDENT_RANK,
    )

    duration_delta = round(
        float(current["runtime_duration_sec"]) - float(base_doc.get("runtime_duration_sec") or 0.0),
        3,
    )
    duration_exceeds = abs(duration_delta) > RUNTIME_DURATION_WARNING_THRESHOLD_SEC

    artifact_drift: list[str] = []
    base_versions = base_doc.get("artifact_versions") or {}
    for name in sorted(set(base_versions) | set(current.get("artifact_versions") or {})):
        bv = base_versions.get(name)
        cv = current.get("artifact_versions", {}).get(name)
        if bv is not None and cv is not None and int(bv) != int(cv):
            artifact_drift.append(f"{name}:{bv}->{cv}")

    summary_delta: dict[str, int] = {}
    cur_sum = current.get("status_summary") or {}
    base_sum = base_doc.get("status_summary") or {}
    for key in ("OK", "WARNING", "FAIL"):
        delta = int(cur_sum.get(key) or 0) - int(base_sum.get(key) or 0)
        if delta != 0:
            summary_delta[key] = delta

    if qual_changed:
        warnings.append("qualification_status_downgrade")
    if incident_changed:
        warnings.append("incident_level_increased")
    if duration_exceeds:
        warnings.append("runtime_duration_delta_exceeds_threshold")
    if artifact_drift:
        warnings.extend([f"artifact_version_drift:{d}" for d in artifact_drift])

    return {
        "baseline_present": True,
        "baseline": base_doc,
        "current": current,
        "qualification_changed": qual_changed,
        "incident_level_changed": incident_changed,
        "runtime_duration_delta_sec": duration_delta,
        "artifact_version_drift": sorted(artifact_drift),
        "status_summary_delta": {k: summary_delta[k] for k in sorted(summary_delta)},
        "failures": sorted(set(failures)),
        "warnings": sorted(set(warnings)),
    }


def build_drift_report(
    output_dir: Path, comparison: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Build deterministic drift report from comparison result."""
    cmp = comparison if comparison is not None else compare_runtime_against_baseline(output_dir)

    failures = list(cmp.get("failures") or [])
    warnings = list(cmp.get("warnings") or [])

    drift_status: DriftStatus = "OK"
    if failures:
        drift_status = "FAIL"
    elif warnings or not cmp.get("baseline_present"):
        drift_status = "WARNING"
        if not cmp.get("baseline_present"):
            warnings = sorted(set(warnings) | {"baseline_not_present"})

    report: dict[str, Any] = {
        "schema_version": BASELINE_SCHEMA_VERSION,
        "generated_at": _utc_now_iso(),
        "drift_status": drift_status,
        "baseline_present": bool(cmp.get("baseline_present")),
        "qualification_changed": bool(cmp.get("qualification_changed")),
        "incident_level_changed": bool(cmp.get("incident_level_changed")),
        "runtime_duration_delta_sec": round(float(cmp.get("runtime_duration_delta_sec") or 0.0), 3),
        "artifact_version_drift": list(cmp.get("artifact_version_drift") or []),
        "status_summary_delta": dict(cmp.get("status_summary_delta") or {}),
        "drift_warnings": sorted(set(warnings)),
        "drift_failures": sorted(set(failures)),
    }
    return {k: report[k] for k in DRIFT_KEY_ORDER}


def write_drift_report(path: Path, report: dict[str, Any]) -> Path:
    dest = path.expanduser().resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)
    ordered = {k: report[k] for k in DRIFT_KEY_ORDER if k in report}
    payload = json.dumps(ordered, indent=2, sort_keys=True, default=str) + "\n"
    tmp = dest.with_name(dest.name + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, dest)
    return dest


def create_runtime_baseline(output_dir: Path) -> Path:
    """Build and atomically write baseline (idempotent snapshot of current state)."""
    baseline = build_runtime_baseline(output_dir)
    return write_runtime_baseline(default_runtime_baseline_path(output_dir), baseline)


def compare_and_write_drift(output_dir: Path) -> tuple[dict[str, Any], Path]:
    """Compare against baseline and atomically write drift report."""
    cmp = compare_runtime_against_baseline(output_dir)
    report = build_drift_report(output_dir, cmp)
    path = write_drift_report(default_drift_report_path(output_dir), report)
    return report, path


def strict_drift_exit_code(report: dict[str, Any], *, strict: bool) -> int:
    st = str(report.get("drift_status") or "FAIL")
    if st == "FAIL":
        return 1
    if strict and st != "OK":
        return 1
    return 0


def render_drift_summary(report: dict[str, Any]) -> str:
    lines = [
        "Runtime drift comparison summary",
        "",
        "Baseline comparison is deterministic operational inspection, not anomaly analytics.",
        "",
        f"Drift status: {report.get('drift_status', 'UNKNOWN')}",
        f"Baseline present: {report.get('baseline_present')}",
        f"Qualification changed: {report.get('qualification_changed')}",
        f"Incident level changed: {report.get('incident_level_changed')}",
        f"Runtime duration delta (sec): {report.get('runtime_duration_delta_sec')}",
    ]
    delta = report.get("status_summary_delta") or {}
    if delta:
        lines.append(
            "Status summary delta: " + ", ".join(f"{k}={delta[k]:+d}" for k in sorted(delta)),
        )
    for key in ("artifact_version_drift", "drift_failures", "drift_warnings"):
        items = report.get(key) or []
        if items:
            lines.append(f"{key}: {', '.join(str(i) for i in items)}")
    return "\n".join(lines) + "\n"
