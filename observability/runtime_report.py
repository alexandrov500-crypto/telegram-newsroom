"""Deterministic latest-only runtime report for offline inspection (stdlib, no telemetry)."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from observability.health_snapshot import (
    default_health_snapshot_path,
    load_health_snapshot,
    load_health_snapshot_sidecar_json,
)
from observability.runtime_schema import CURRENT_RUNTIME_SCHEMA_VERSION

RUNTIME_REPORT_REL = Path("runtime") / "runtime_report.json"
RUNTIME_REPORT_SCHEMA_VERSION = CURRENT_RUNTIME_SCHEMA_VERSION

IncidentLevel = Literal["NONE", "WARNING", "ERROR"]

REPORT_KEY_ORDER: tuple[str, ...] = (
    "schema_version",
    "artifact_inventory",
    "generated_at",
    "health_snapshot_path",
    "incident_level",
    "incident_summary",
    "pipeline_status",
    "qualification_status",
    "runtime_bundle",
    "runtime_duration_sec",
    "step_status",
    "warnings",
)

STEP_STATUS_DOMAINS: tuple[str, ...] = (
    "ingestion",
    "clustering",
    "summarization",
    "publishing",
)

DOMAIN_OPS_STEPS: dict[str, tuple[str, ...]] = {
    "ingestion": ("preflight", "benchmark"),
    "clustering": ("soak", "bundle"),
    "summarization": ("regression", "qualification"),
    "publishing": ("dashboard", "retention"),
}

_STATUS_RANK = {"OK": 0, "SKIPPED": 1, "WARNING": 2, "FAIL": 3, "ERROR": 3}


@dataclass(frozen=True)
class RuntimeReportInputs:
    ops_report: dict[str, Any]
    output_dir: Path
    health_snapshot: dict[str, Any] | None = None
    health_snapshot_path: Path | None = None


def default_runtime_report_path(base_dir: Path) -> Path:
    return base_dir.expanduser().resolve() / RUNTIME_REPORT_REL


def _utc_now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _bundle_inventory(output_dir: Path) -> tuple[dict[str, Any], list[str]]:
    zp = output_dir / "runtime_bundle.zip"
    warns: list[str] = []
    if not zp.is_file():
        warns.append("missing:runtime_bundle.zip")
        return {"exists": False, "modified_at": None, "size_mb": None}, warns
    try:
        st = zp.stat()
        mtime = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(st.st_mtime))
        size_mb = round(st.st_size / (1024 * 1024), 4)
    except OSError as exc:
        warns.append(f"runtime_bundle_stat:{exc!r}")
        return {"exists": True, "modified_at": None, "size_mb": None}, warns
    return {"exists": True, "modified_at": mtime, "size_mb": size_mb}, warns


def _artifact_inventory(output_dir: Path, health_path: Path | None) -> dict[str, bool]:
    hp = health_path if health_path is not None else default_health_snapshot_path(output_dir)
    return {
        "health_snapshot": hp.is_file(),
        "qualification_report": (output_dir / "qualification.json").is_file(),
        "runtime_bundle": (output_dir / "runtime_bundle.zip").is_file(),
    }


def _step_status_from_ops(
    ops_report: dict[str, Any],
    health: dict[str, Any],
    output_dir: Path,
) -> dict[str, str]:
    by_name: dict[str, str] = {}
    for step in ops_report.get("steps") or []:
        if isinstance(step, dict):
            name = str(step.get("name") or "")
            if name:
                by_name[name] = str(step.get("status") or "OK").upper()

    out: dict[str, str] = {}
    for domain, names in DOMAIN_OPS_STEPS.items():
        worst = "OK"
        for n in names:
            st = by_name.get(n, "SKIPPED")
            if _STATUS_RANK.get(st, 0) > _STATUS_RANK.get(worst, 0):
                worst = "FAIL" if st == "FAIL" else st
        out[domain] = worst

    bench = load_health_snapshot_sidecar_json(output_dir / "ops_benchmark.json")
    if bench:
        counters = dict((bench.get("metrics_export") or {}).get("counters") or {})
        pub_fails = int(counters.get("publish_failures") or 0)
        if pub_fails > 0 and out["publishing"] == "OK":
            out["publishing"] = "WARNING"
    failed = health.get("failed_steps") or []
    if failed and out["publishing"] == "OK":
        if any(x in failed for x in ("dashboard", "retention")):
            out["publishing"] = "WARNING"

    return {k: out[k] for k in STEP_STATUS_DOMAINS}


def build_incident_summary(
    *,
    health_snapshot: dict[str, Any],
    qualification_status: str | None,
    artifact_inventory: dict[str, bool],
    report_warnings: list[str],
) -> tuple[IncidentLevel, list[str], list[str]]:
    """
    Classify incident level (no alerting).

    Rules: failed_steps → ERROR; qualification WARNING → WARNING;
    qualification FAIL → ERROR; missing optional artifacts → WARNING; else NONE.
    """
    level: IncidentLevel = "NONE"
    summary: list[str] = []
    warnings = sorted(set(report_warnings))

    failed = list(health_snapshot.get("failed_steps") or [])
    if failed:
        level = "ERROR"
        summary.append(f"failed_steps:{','.join(sorted(failed))}")

    qual = (qualification_status or "").upper()
    if qual == "FAIL":
        level = "ERROR"
        summary.append("qualification_status:FAIL")
    elif qual == "WARNING" and level != "ERROR":
        level = "WARNING"
        summary.append("qualification_status:WARNING")

    optional_keys = ("runtime_bundle", "qualification_report")
    for key in optional_keys:
        if not artifact_inventory.get(key, False):
            if level != "ERROR":
                level = "WARNING"
            msg = f"missing_artifact:{key}"
            summary.append(msg)
            warnings.append(msg)

    if not artifact_inventory.get("health_snapshot", False):
        if level != "ERROR":
            level = "WARNING"
        msg = "missing_artifact:health_snapshot"
        summary.append(msg)
        warnings.append(msg)

    pipeline = str(health_snapshot.get("pipeline_status") or "").upper()
    if pipeline == "FAIL" and level != "ERROR":
        level = "ERROR"
        summary.append("pipeline_status:FAIL")
    elif pipeline == "WARNING" and level == "NONE":
        level = "WARNING"
        summary.append("pipeline_status:WARNING")

    return level, sorted(summary), warnings


def build_runtime_report(
    *,
    ops_report: dict[str, Any],
    output_dir: Path,
    health_snapshot: dict[str, Any] | None = None,
    health_snapshot_path: Path | None = None,
) -> dict[str, Any]:
    """Build deterministic runtime report JSON from ops output and health snapshot."""
    od = output_dir.expanduser().resolve()
    hp = (
        health_snapshot_path.expanduser().resolve()
        if health_snapshot_path
        else default_health_snapshot_path(od)
    )
    health = health_snapshot if health_snapshot is not None else load_health_snapshot(hp)
    if health is None:
        health = {
            "pipeline_status": str(ops_report.get("status") or "UNKNOWN"),
            "runtime_duration_sec": 0.0,
            "failed_steps": [],
            "qualification_status": None,
        }

    bundle_meta, bundle_warns = _bundle_inventory(od)
    inventory = _artifact_inventory(od, hp)
    qual = health.get("qualification_status")
    if qual is None:
        qdoc = load_health_snapshot_sidecar_json(od / "qualification.json")
        if qdoc:
            qual = qdoc.get("qualification_status")

    step_status = _step_status_from_ops(ops_report, health, od)
    incident_level, incident_summary, warnings = build_incident_summary(
        health_snapshot=health,
        qualification_status=str(qual) if qual is not None else None,
        artifact_inventory=inventory,
        report_warnings=bundle_warns,
    )

    report: dict[str, Any] = {
        "schema_version": RUNTIME_REPORT_SCHEMA_VERSION,
        "generated_at": _utc_now_iso(),
        "pipeline_status": str(
            health.get("pipeline_status") or ops_report.get("status") or "UNKNOWN"
        ),
        "runtime_duration_sec": float(health.get("runtime_duration_sec") or 0.0),
        "health_snapshot_path": str(hp),
        "qualification_status": str(qual) if qual is not None else None,
        "incident_level": incident_level,
        "incident_summary": incident_summary,
        "warnings": warnings,
        "artifact_inventory": {k: bool(inventory[k]) for k in sorted(inventory)},
        "step_status": {k: step_status[k] for k in STEP_STATUS_DOMAINS},
        "runtime_bundle": bundle_meta,
    }
    return {k: report[k] for k in REPORT_KEY_ORDER}


def build_runtime_report_from_inputs(inputs: RuntimeReportInputs) -> dict[str, Any]:
    od = inputs.output_dir.expanduser().resolve()
    hp = inputs.health_snapshot_path or default_health_snapshot_path(od)
    health = inputs.health_snapshot
    if health is None and hp.is_file():
        health = load_health_snapshot(hp)
    return build_runtime_report(
        ops_report=inputs.ops_report,
        output_dir=od,
        health_snapshot=health,
        health_snapshot_path=hp,
    )


def write_runtime_report(path: Path, report: dict[str, Any]) -> Path:
    dest = path.expanduser().resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)
    ordered = {k: report[k] for k in REPORT_KEY_ORDER if k in report}
    payload = json.dumps(ordered, indent=2, sort_keys=True, default=str) + "\n"
    tmp = dest.with_name(dest.name + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, dest)
    return dest


def load_runtime_report(path: Path) -> dict[str, Any] | None:
    dest = path.expanduser().resolve()
    if not dest.is_file():
        return None
    try:
        data = json.loads(dest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return None
    return data if isinstance(data, dict) else None


def resolve_runtime_report_path(path: Path | None, *, output_dir: Path | None) -> Path | None:
    if path is not None:
        p = path.expanduser().resolve()
        if p.is_dir():
            return default_runtime_report_path(p)
        if p.name == "health_snapshot.json":
            return default_runtime_report_path(p.parent.parent)
        return p
    if output_dir is not None:
        return default_runtime_report_path(output_dir)
    return None


def render_runtime_report_summary(report: dict[str, Any]) -> str:
    lines = [
        "Runtime report summary",
        "",
        f"Pipeline status: {report.get('pipeline_status', 'UNKNOWN')}",
        f"Incident level: {report.get('incident_level', 'NONE')}",
        f"Runtime duration: {report.get('runtime_duration_sec', 0)} sec",
    ]
    qual = report.get("qualification_status")
    if qual is not None:
        lines.append(f"Qualification status: {qual}")
    inv = report.get("artifact_inventory") or {}
    lines.append(
        "Artifacts: " + ", ".join(f"{k}={'yes' if inv.get(k) else 'no'}" for k in sorted(inv)),
    )
    rb = report.get("runtime_bundle") or {}
    if rb.get("exists"):
        lines.append(f"Runtime bundle: {rb.get('size_mb')} MB (modified {rb.get('modified_at')})")
    steps = report.get("step_status") or {}
    if steps:
        lines.append("")
        lines.append("Step status:")
        for k in STEP_STATUS_DOMAINS:
            lines.append(f"  {k}: {steps.get(k, 'UNKNOWN')}")
    summ = report.get("incident_summary") or []
    if summ:
        lines.append("")
        lines.append("Incident summary:")
        for s in summ:
            lines.append(f"  - {s}")
    return "\n".join(lines) + "\n"


def strict_report_exit_code(report: dict[str, Any]) -> int:
    return 0 if str(report.get("incident_level") or "NONE") == "NONE" else 1
