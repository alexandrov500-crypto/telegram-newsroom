"""Bounded qualification history and deterministic audit snapshots (stdlib)."""

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
from observability.runtime_manifest import default_runtime_manifest_path, load_runtime_manifest
from observability.runtime_report import default_runtime_report_path, load_runtime_report
from observability.runtime_schema import CURRENT_RUNTIME_SCHEMA_VERSION
from observability.runtime_verify import verify_runtime_manifest

AuditStatus = Literal["OK", "WARNING", "FAIL"]

QUALIFICATION_HISTORY_REL = Path("runtime") / "qualification_history.json"
AUDIT_SNAPSHOT_REL = Path("runtime") / "audit_snapshot.json"

HISTORY_LIMIT = 20
HISTORY_SCHEMA_VERSION = CURRENT_RUNTIME_SCHEMA_VERSION

HISTORY_KEY_ORDER: tuple[str, ...] = (
    "entries",
    "history_limit",
    "schema_version",
)

ENTRY_KEY_ORDER: tuple[str, ...] = (
    "bundle_status",
    "compatibility_status",
    "incident_level",
    "qualification_status",
    "recovery_status",
    "runtime_duration_sec",
    "timestamp",
    "verification_status",
)

AUDIT_KEY_ORDER: tuple[str, ...] = (
    "audit_status",
    "generated_at",
    "history_entries",
    "latest_incident_level",
    "latest_qualification_status",
    "recent_failures",
    "recent_warnings",
    "schema_version",
    "status_summary",
)


def default_qualification_history_path(base_dir: Path) -> Path:
    return base_dir.expanduser().resolve() / QUALIFICATION_HISTORY_REL


def default_audit_snapshot_path(base_dir: Path) -> Path:
    return base_dir.expanduser().resolve() / AUDIT_SNAPSHOT_REL


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


def _normalize_entry(entry: dict[str, Any]) -> dict[str, Any]:
    row: dict[str, Any] = {
        "timestamp": str(entry.get("timestamp") or _utc_now_iso()),
        "qualification_status": _status_str(entry.get("qualification_status")),
        "verification_status": _status_str(entry.get("verification_status")),
        "recovery_status": _status_str(entry.get("recovery_status")),
        "compatibility_status": _status_str(entry.get("compatibility_status")),
        "incident_level": str(entry.get("incident_level") or "NONE").upper(),
        "runtime_duration_sec": round(float(entry.get("runtime_duration_sec") or 0.0), 3),
        "bundle_status": _status_str(entry.get("bundle_status")),
    }
    return {k: row[k] for k in ENTRY_KEY_ORDER}


def collect_history_entry_from_output_dir(
    output_dir: Path,
    *,
    timestamp: str | None = None,
    recovery_report: dict[str, Any] | None = None,
    compatibility_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one history entry from lightweight ops metadata (no logs/payloads)."""
    base = output_dir.expanduser().resolve()
    qual = load_health_snapshot_sidecar_json(base / "qualification.json")
    rpt = load_runtime_report(default_runtime_report_path(base))
    snap = load_health_snapshot(default_health_snapshot_path(base))
    manifest = load_runtime_manifest(default_runtime_manifest_path(base))

    recovery = recovery_report
    if recovery is None:
        recovery = _load_json(base / "runtime" / "recovery_report.json")

    compat = compatibility_report
    if compat is None:
        compat = _load_json(base / "runtime" / "compatibility_report.json")

    verification = verify_runtime_manifest(output_dir=base)

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
        duration = float(snap.get("runtime_duration_sec") or 0.0)

    bundle_st = "OK"
    if manifest:
        bundle_st = _status_str(manifest.get("bundle_status"))

    return _normalize_entry(
        {
            "timestamp": timestamp or _utc_now_iso(),
            "qualification_status": qual_st,
            "verification_status": recovery.get("verification_status")
            if recovery
            else verification.get("verification_status"),
            "recovery_status": recovery.get("recovery_status") if recovery else "OK",
            "compatibility_status": compat.get("compatibility_status") if compat else "OK",
            "incident_level": incident,
            "runtime_duration_sec": duration,
            "bundle_status": bundle_st,
        },
    )


def _empty_history() -> dict[str, Any]:
    return {
        "schema_version": HISTORY_SCHEMA_VERSION,
        "history_limit": HISTORY_LIMIT,
        "entries": [],
    }


def load_qualification_history(path: Path) -> dict[str, Any]:
    """Load history document or return an empty bounded template."""
    dest = path.expanduser().resolve()
    data = _load_json(dest)
    if data is None:
        return _empty_history()
    limit = int(data.get("history_limit") or HISTORY_LIMIT)
    entries = data.get("entries") or []
    if not isinstance(entries, list):
        entries = []
    normalized = [_normalize_entry(e) for e in entries if isinstance(e, dict)]
    return rotate_qualification_history(
        {
            "schema_version": int(data.get("schema_version") or HISTORY_SCHEMA_VERSION),
            "history_limit": limit,
            "entries": normalized,
        },
    )


def rotate_qualification_history(history: dict[str, Any]) -> dict[str, Any]:
    """Trim entries to ``history_limit`` (latest-first, deterministic)."""
    limit = int(history.get("history_limit") or HISTORY_LIMIT)
    entries = list(history.get("entries") or [])
    if not isinstance(entries, list):
        entries = []
    normalized = [_normalize_entry(e) for e in entries if isinstance(e, dict)]
    # Latest-first: sort by timestamp descending, stable tie-breaker on qualification_status.
    normalized.sort(
        key=lambda e: (str(e["timestamp"]), str(e["qualification_status"])), reverse=True
    )
    trimmed = normalized[:limit]
    doc = {
        "schema_version": int(history.get("schema_version") or HISTORY_SCHEMA_VERSION),
        "history_limit": limit,
        "entries": trimmed,
    }
    return {k: doc[k] for k in HISTORY_KEY_ORDER}


def write_qualification_history(path: Path, history: dict[str, Any]) -> Path:
    dest = path.expanduser().resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)
    rotated = rotate_qualification_history(history)
    ordered = {k: rotated[k] for k in HISTORY_KEY_ORDER}
    payload = json.dumps(ordered, indent=2, sort_keys=True, default=str) + "\n"
    tmp = dest.with_name(dest.name + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, dest)
    return dest


def append_qualification_history(
    output_dir: Path,
    entry: dict[str, Any],
    *,
    history_path: Path | None = None,
) -> Path:
    """Append one entry (latest-first) with bounded rotation; atomic write."""
    dest = history_path or default_qualification_history_path(output_dir)
    history = load_qualification_history(dest)
    new_entry = _normalize_entry(entry)
    entries = [new_entry]
    for existing in history.get("entries") or []:
        if isinstance(existing, dict):
            if existing.get("timestamp") == new_entry.get("timestamp") and existing.get(
                "qualification_status",
            ) == new_entry.get("qualification_status"):
                continue
            entries.append(_normalize_entry(existing))
    history["entries"] = entries
    return write_qualification_history(dest, history)


def _entry_aggregate_status(entry: dict[str, Any]) -> AuditStatus:
    fields = (
        "qualification_status",
        "verification_status",
        "recovery_status",
        "compatibility_status",
        "bundle_status",
    )
    if any(_status_str(entry.get(f)) == "FAIL" for f in fields):
        return "FAIL"
    if any(_status_str(entry.get(f)) == "WARNING" for f in fields):
        return "WARNING"
    if str(entry.get("incident_level") or "NONE").upper() not in ("NONE", "OK"):
        if str(entry.get("incident_level")).upper() == "ERROR":
            return "FAIL"
        return "WARNING"
    return "OK"


def _collect_recent_warnings(output_dir: Path, limit: int = 8) -> list[str]:
    base = output_dir.expanduser().resolve()
    warnings: list[str] = []
    recovery = _load_json(base / "runtime" / "recovery_report.json")
    compat = _load_json(base / "runtime" / "compatibility_report.json")
    rpt = load_runtime_report(default_runtime_report_path(base))
    if recovery:
        warnings.extend(str(w) for w in (recovery.get("recovery_warnings") or [])[:limit])
    if compat:
        warnings.extend(str(w) for w in (compat.get("compatibility_warnings") or [])[:limit])
    if rpt:
        warnings.extend(str(w) for w in (rpt.get("warnings") or [])[:limit])
    return sorted(set(warnings))[:limit]


def _collect_recent_failures(history: dict[str, Any], limit: int = 8) -> list[str]:
    failures: list[str] = []
    for entry in history.get("entries") or []:
        if not isinstance(entry, dict):
            continue
        ts = str(entry.get("timestamp") or "")
        if _status_str(entry.get("qualification_status")) == "FAIL":
            failures.append(f"{ts}:qualification_status:FAIL")
        if _status_str(entry.get("recovery_status")) == "FAIL":
            failures.append(f"{ts}:recovery_status:FAIL")
        if _status_str(entry.get("verification_status")) == "FAIL":
            failures.append(f"{ts}:verification_status:FAIL")
        if _status_str(entry.get("compatibility_status")) == "FAIL":
            failures.append(f"{ts}:compatibility_status:FAIL")
    return sorted(set(failures), reverse=True)[:limit]


def build_audit_snapshot(
    output_dir: Path,
    history: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build deterministic audit snapshot from bounded qualification history."""
    base = output_dir.expanduser().resolve()
    hist = (
        history
        if history is not None
        else load_qualification_history(
            default_qualification_history_path(base),
        )
    )
    entries = list(hist.get("entries") or [])

    summary: dict[str, int] = {"OK": 0, "WARNING": 0, "FAIL": 0}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        st = _status_str(entry.get("qualification_status"))
        if st in summary:
            summary[st] += 1

    latest_qual = "OK"
    latest_incident = "NONE"
    audit: AuditStatus = "OK"
    if entries:
        latest = entries[0] if isinstance(entries[0], dict) else {}
        latest_qual = _status_str(latest.get("qualification_status"))
        latest_incident = str(latest.get("incident_level") or "NONE").upper()
        audit = _entry_aggregate_status(latest)
    else:
        audit = "WARNING"

    snapshot: dict[str, Any] = {
        "schema_version": HISTORY_SCHEMA_VERSION,
        "generated_at": _utc_now_iso(),
        "audit_status": audit,
        "history_entries": len(entries),
        "latest_qualification_status": latest_qual,
        "latest_incident_level": latest_incident,
        "status_summary": {k: summary[k] for k in ("OK", "WARNING", "FAIL") if k in summary},
        "recent_failures": _collect_recent_failures(hist),
        "recent_warnings": _collect_recent_warnings(base),
    }
    return {k: snapshot[k] for k in AUDIT_KEY_ORDER}


def write_audit_snapshot(path: Path, snapshot: dict[str, Any]) -> Path:
    dest = path.expanduser().resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)
    ordered = {k: snapshot[k] for k in AUDIT_KEY_ORDER if k in snapshot}
    payload = json.dumps(ordered, indent=2, sort_keys=True, default=str) + "\n"
    tmp = dest.with_name(dest.name + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, dest)
    return dest


def update_runtime_history(
    output_dir: Path,
    *,
    entry: dict[str, Any] | None = None,
    recovery_report: dict[str, Any] | None = None,
    compatibility_report: dict[str, Any] | None = None,
) -> tuple[Path, Path]:
    """Append history entry and refresh audit snapshot (atomic, bounded)."""
    base = output_dir.expanduser().resolve()
    row = entry or collect_history_entry_from_output_dir(
        base,
        recovery_report=recovery_report,
        compatibility_report=compatibility_report,
    )
    hist_path = append_qualification_history(base, row)
    hist = load_qualification_history(hist_path)
    audit = build_audit_snapshot(base, history=hist)
    audit_path = write_audit_snapshot(default_audit_snapshot_path(base), audit)
    return hist_path, audit_path


def strict_audit_exit_code(snapshot: dict[str, Any], *, strict: bool) -> int:
    latest = _status_str(snapshot.get("latest_qualification_status"))
    audit = _status_str(snapshot.get("audit_status"))
    if audit == "FAIL" or latest == "FAIL":
        return 1
    if strict and (audit != "OK" or latest != "OK"):
        return 1
    return 0


def render_audit_summary(snapshot: dict[str, Any], history: dict[str, Any] | None = None) -> str:
    lines = [
        "Runtime audit summary",
        "",
        "Audit snapshots are operational inspection artifacts, not compliance archives.",
        "",
        f"Audit status: {snapshot.get('audit_status', 'UNKNOWN')}",
        f"Latest qualification status: {snapshot.get('latest_qualification_status')}",
        f"Latest incident level: {snapshot.get('latest_incident_level')}",
        f"History entries: {snapshot.get('history_entries', 0)}",
    ]
    summary = snapshot.get("status_summary") or {}
    if summary:
        lines.append(
            "Status summary: " + ", ".join(f"{k}={summary[k]}" for k in sorted(summary)),
        )
    for key in ("recent_failures", "recent_warnings"):
        items = snapshot.get(key) or []
        if items:
            lines.append(f"{key}:")
            for item in items[:12]:
                lines.append(f"  {item}")
    if history and history.get("entries"):
        lines.append("")
        lines.append("Recent qualification history (latest first):")
        for ent in (history.get("entries") or [])[:5]:
            if isinstance(ent, dict):
                lines.append(
                    f"  {ent.get('timestamp')} qual={ent.get('qualification_status')} "
                    f"incident={ent.get('incident_level')}",
                )
    return "\n".join(lines) + "\n"
