"""Lightweight release qualification from runtime bundles (read-only, deterministic)."""

from __future__ import annotations

import json
import math
import os
import time
from pathlib import Path
from typing import Any, Literal

from utils.runtime_regression import (
    classify_regression,
    load_runtime_bundle,
    run_regression_comparison,
)

QualificationStatus = Literal["OK", "WARNING", "FAIL"]
CheckStatus = Literal["OK", "WARNING", "FAIL"]

# Alphabetical: matches ``json.dumps(..., sort_keys=True)`` key order for stable nested JSON.
CHECK_ORDER: tuple[str, ...] = (
    "bundle_load",
    "integrity",
    "queue_health",
    "regression",
    "runtime_state",
    "soak",
)

# Human-readable report order (operational semantics, not JSON key order).
REPORT_ORDER: tuple[str, ...] = (
    "integrity",
    "regression",
    "queue_health",
    "runtime_state",
    "soak",
    "bundle_load",
)

DISPLAY_LABELS: dict[str, str] = {
    "bundle_load": "Bundle load",
    "integrity": "Integrity",
    "queue_health": "Queue health",
    "regression": "Regression",
    "runtime_state": "Runtime state",
    "soak": "Soak",
}

QUEUE_METRICS: frozenset[str] = frozenset(
    {
        "avg_oldest_pending_age_sec_sampled_kinds",
        "queue_pressure_score",
        "pending_jobs_total",
    },
)

RUNTIME_STATE_KEYS: tuple[str, ...] = (
    "timeline_events",
    "timeline_file_bytes",
    "suppression_entries",
    "event_history_events",
    "drift_snapshots",
)

CRITICAL_HARD_FILES: tuple[str, ...] = ("benchmark.json", "stability.json")
CRITICAL_SOFT_FILES: tuple[str, ...] = ("integrity.json", "manifest.json", "runtime_summary.json")


def _num(x: Any) -> float | None:
    if x is None:
        return None
    try:
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    except (TypeError, ValueError):
        return None


def load_release_inputs(current_zip: Path, baseline_zip: Path) -> dict[str, Any]:
    """Load both bundles via ``load_runtime_bundle`` (re-use regression loader)."""
    c_load, c_warn = load_runtime_bundle(current_zip)
    b_load, b_warn = load_runtime_bundle(baseline_zip)
    return {
        "baseline_load": b_load,
        "baseline_warnings": list(b_warn),
        "current_load": c_load,
        "current_warnings": list(c_warn),
    }


def _fatal_parse_warnings(warnings: list[str]) -> list[str]:
    out: list[str] = []
    for w in warnings:
        if any(
            tag in w
            for tag in (
                "bad_zip:",
                "invalid_json:",
                "bundle_not_found:",
                "zip_read_failed:",
            )
        ):
            out.append(w)
    return sorted(out)


def evaluate_bundle_load(
    current_warnings: list[str],
    baseline_warnings: list[str],
    current_loaded: dict[str, Any],
) -> dict[str, Any]:
    detail: dict[str, Any] = {}
    worst: CheckStatus = "OK"

    cf = _fatal_parse_warnings(current_warnings)
    bf = _fatal_parse_warnings(baseline_warnings)
    if cf:
        detail["current_fatal"] = cf
        worst = "FAIL"
    if bf:
        detail["baseline_fatal"] = bf
        worst = "FAIL"

    soft: list[str] = []
    if current_warnings and not cf:
        soft.append("current_parse_warnings")
        detail["current_warnings"] = sorted(current_warnings)
    if baseline_warnings and not bf:
        soft.append("baseline_parse_warnings")
        detail["baseline_warnings"] = sorted(baseline_warnings)
    if soft and worst == "OK":
        worst = "WARNING"

    crit = evaluate_critical_artifacts(current_loaded)
    cr_st = str(crit.get("status") or "OK")
    if _rank(cr_st) > _rank(worst):  # type: ignore[arg-type]
        worst = cr_st  # type: ignore[assignment]
    if crit.get("detail"):
        detail["critical_files"] = crit["detail"]

    return {"detail": {k: detail[k] for k in sorted(detail)}, "status": worst}


def evaluate_critical_artifacts(loaded: dict[str, Any]) -> dict[str, Any]:
    missing_hard = sorted(n for n in CRITICAL_HARD_FILES if n not in loaded)
    if missing_hard:
        return {"detail": {"missing_required": missing_hard}, "status": "FAIL"}
    missing_soft = sorted(n for n in CRITICAL_SOFT_FILES if n not in loaded)
    if missing_soft:
        return {"detail": {"missing_recommended": missing_soft}, "status": "WARNING"}
    return {"detail": {}, "status": "OK"}


def evaluate_integrity(
    integrity_doc: dict[str, Any] | None,
    *,
    require_clean: bool,
) -> dict[str, Any]:
    if integrity_doc is None:
        st: CheckStatus = "FAIL" if require_clean else "WARNING"
        return {"detail": {"reason": "integrity_json_absent"}, "status": st}
    issues: list[str] = []
    for key in ("event_history_issues", "suppression_issues", "timeline_issues"):
        chunk = integrity_doc.get(key) or []
        if isinstance(chunk, list):
            issues.extend(str(x) for x in chunk)
    if issues:
        if require_clean:
            return {"detail": {"issues": sorted(issues)[:200]}, "status": "FAIL"}
        return {"detail": {"issues": sorted(issues)[:200]}, "status": "WARNING"}
    return {"detail": {}, "status": "OK"}


def evaluate_regressions(
    regression_payload: dict[str, Any],
    *,
    require_regression_ok: bool,
) -> dict[str, Any]:
    """
    Map regression ``overall_status`` to a check status.

    ``WARNING`` is always surfaced on this check when the regression payload is
    ``WARNING``; ``--allow-warning`` only affects top-level ``release_ready``.
    """
    overall = str(regression_payload.get("overall_status") or "OK")
    detail: dict[str, Any] = {"overall": overall}
    if overall == "FAIL":
        return {"detail": detail, "status": "FAIL"}
    if require_regression_ok and overall != "OK":
        return {"detail": detail, "status": "FAIL"}
    if overall == "WARNING":
        return {"detail": detail, "status": "WARNING"}
    return {"detail": detail, "status": "OK"}


def evaluate_queue_health(regression_payload: dict[str, Any]) -> dict[str, Any]:
    rows = regression_payload.get("metrics") or []
    worst: CheckStatus = "OK"
    flagged: list[str] = []
    if not isinstance(rows, list):
        return {"detail": {}, "status": "OK"}
    for row in rows:
        if not isinstance(row, dict):
            continue
        m = str(row.get("metric") or "")
        if m not in QUEUE_METRICS:
            continue
        st = str(row.get("status") or "OK")
        if st == "FAIL":
            return {"detail": {"metric": m, "row": row}, "status": "FAIL"}
        if st == "WARNING":
            worst = "WARNING"
            flagged.append(m)
    return {"detail": {"warning_metrics": sorted(flagged)}, "status": worst}


def evaluate_runtime_state(
    current_summary: dict[str, Any] | None,
    baseline_summary: dict[str, Any] | None,
    *,
    warn_pct: float,
    fail_pct: float,
) -> dict[str, Any]:
    cb = (current_summary or {}).get("bounded_state_report") or {}
    bb = (baseline_summary or {}).get("bounded_state_report") or {}
    worst: CheckStatus = "OK"
    details: list[dict[str, Any]] = []
    raw = os.getenv("NEWSROOM_QUALIFICATION_SKIP_RUNTIME_KEYS", "").strip()
    skip = frozenset(x.strip() for x in raw.split(",") if x.strip()) if raw else frozenset()
    for key in RUNTIME_STATE_KEYS:
        if key in skip:
            details.append(
                {"key": key, "notes": ["qualification_skipped:configured"], "pct_change": None, "status": "OK"},
            )
            continue
        st, pct, _rw = classify_regression(
            baseline=_num(bb.get(key)),
            current=_num(cb.get(key)),
            warn_pct=warn_pct,
            fail_pct=fail_pct,
            ignore_missing=True,
        )
        details.append({"key": key, "pct_change": pct, "status": st})
        if st == "FAIL":
            return {"detail": {"rows": sorted(details, key=lambda r: r["key"])}, "status": "FAIL"}
        if st == "WARNING":
            worst = "WARNING"
    return {"detail": {"rows": sorted(details, key=lambda r: r["key"])}, "status": worst}


def evaluate_soak(
    soak_doc: dict[str, Any] | None,
    *,
    require_soak: bool,
    soak_in_manifest_missing: bool,
) -> dict[str, Any]:
    if require_soak and soak_doc is None:
        return {"detail": {"reason": "soak_report_required"}, "status": "FAIL"}
    if soak_doc is None:
        return {"detail": {"reason": "soak_report_absent"}, "status": "OK"}
    br = soak_doc.get("bounded_report") or {}
    ok = bool(br.get("ok")) if isinstance(br, dict) else False
    wrn = soak_doc.get("warnings") or []
    if not isinstance(wrn, list):
        wrn = []
    if not ok or wrn:
        return {"detail": {"bounded_ok": ok, "warnings": wrn[:48]}, "status": "FAIL"}
    detail: dict[str, Any] = {"bounded_ok": True}
    if soak_in_manifest_missing:
        detail["note"] = "soak_report_listed_missing_in_manifest_but_present_in_zip"
    return {"detail": detail, "status": "OK"}


def _rank(st: str) -> int:
    return {"OK": 0, "WARNING": 1, "FAIL": 2}.get(st, 0)


def evaluate_release_qualification(
    current_zip: Path,
    baseline_zip: Path,
    *,
    warn_pct: float,
    fail_pct: float,
    allow_warning: bool,
    strict: bool,
    require_soak: bool,
    require_integrity_clean: bool,
    require_regression_ok: bool,
) -> tuple[dict[str, Any], int]:
    inputs = load_release_inputs(current_zip, baseline_zip)
    c_load: dict[str, Any] = inputs["current_load"]
    b_load: dict[str, Any] = inputs["baseline_load"]
    c_warn: list[str] = inputs["current_warnings"]
    b_warn: list[str] = inputs["baseline_warnings"]

    raw = os.getenv("NEWSROOM_REGRESSION_SKIP_METRICS", "").strip()
    reg_skip = frozenset(x.strip() for x in raw.split(",") if x.strip()) if raw else None
    reg_payload, _reg_code = run_regression_comparison(
        baseline_zip,
        current_zip,
        warn_pct=warn_pct,
        fail_pct=fail_pct,
        strict=False,
        ignore_missing=True,
        regression_skip_metrics=reg_skip,
    )

    manifest = c_load.get("manifest.json") if isinstance(c_load.get("manifest.json"), dict) else {}
    missing = manifest.get("missing_files") or []
    soak_missing_in_manifest = isinstance(missing, list) and "soak_report.json" in missing

    checks: dict[str, dict[str, Any]] = {}
    checks["bundle_load"] = evaluate_bundle_load(c_warn, b_warn, c_load)
    checks["integrity"] = evaluate_integrity(
        c_load.get("integrity.json") if isinstance(c_load.get("integrity.json"), dict) else None,
        require_clean=require_integrity_clean,
    )
    checks["regression"] = evaluate_regressions(
        reg_payload,
        require_regression_ok=require_regression_ok,
    )
    checks["queue_health"] = evaluate_queue_health(reg_payload)
    checks["runtime_state"] = evaluate_runtime_state(
        c_load.get("runtime_summary.json") if isinstance(c_load.get("runtime_summary.json"), dict) else None,
        b_load.get("runtime_summary.json") if isinstance(b_load.get("runtime_summary.json"), dict) else None,
        warn_pct=warn_pct,
        fail_pct=fail_pct,
    )
    soak_raw = c_load.get("soak_report.json")
    soak_doc = soak_raw if isinstance(soak_raw, dict) else None
    checks["soak"] = evaluate_soak(soak_doc, require_soak=require_soak, soak_in_manifest_missing=soak_missing_in_manifest)

    failures: list[str] = []
    warns: list[str] = []
    worst: QualificationStatus = "OK"
    for name in CHECK_ORDER:
        block = checks.get(name) or {}
        st = str(block.get("status") or "OK")
        if _rank(st) > _rank(worst):
            worst = st  # type: ignore[assignment]
        if st == "FAIL":
            failures.append(f"{name}:{json.dumps(block.get('detail'), sort_keys=True, default=str)[:400]}")
        elif st == "WARNING":
            warns.append(f"{name}:{json.dumps(block.get('detail'), sort_keys=True, default=str)[:400]}")

    has_fail = any(str((checks[k] or {}).get("status")) == "FAIL" for k in CHECK_ORDER)
    has_warn = any(str((checks[k] or {}).get("status")) == "WARNING" for k in CHECK_ORDER)
    qualification_status: QualificationStatus
    if has_fail:
        qualification_status = "FAIL"
    elif has_warn:
        qualification_status = "WARNING"
    else:
        qualification_status = "OK"

    release_ready = not has_fail and (not has_warn or allow_warning)

    out: dict[str, Any] = {
        "baseline_bundle": str(baseline_zip.resolve()),
        "checks": {k: checks[k] for k in CHECK_ORDER},
        "evaluated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "failures": sorted(failures),
        "qualification_status": qualification_status,
        "release_ready": bool(release_ready),
        "runtime_bundle": str(current_zip.resolve()),
        "threshold_config": {
            "allow_warning": allow_warning,
            "fail_threshold_pct": fail_pct,
            "require_integrity_clean": require_integrity_clean,
            "require_regression_ok": require_regression_ok,
            "require_soak": require_soak,
            "strict": strict,
            "warning_threshold_pct": warn_pct,
        },
        "warnings": sorted(warns),
    }

    exit_code = 0
    if not release_ready:
        exit_code = 1
    if strict:
        if qualification_status != "OK":
            exit_code = 1
        rw = reg_payload.get("warnings") or []
        if rw:
            exit_code = 1

    return out, exit_code


def render_release_report(result: dict[str, Any]) -> str:
    lines = [
        "Release qualification summary",
        "",
        f"runtime_bundle: {result.get('runtime_bundle')}",
        f"baseline_bundle: {result.get('baseline_bundle')}",
        "",
    ]
    checks = result.get("checks") or {}
    for name in REPORT_ORDER:
        block = checks.get(name) or {}
        label = DISPLAY_LABELS.get(name, name.replace("_", " ").title())
        st = str(block.get("status") or "OK")
        if name == "soak" and st == "OK":
            detail = block.get("detail") or {}
            if detail.get("reason") == "soak_report_absent":
                st = "MISSING"
        lines.append(f"{label}: {st}")
    lines.extend(
        [
            "",
            f"Qualification status: {result.get('qualification_status')}",
            f"RELEASE_READY: {str(bool(result.get('release_ready'))).lower()}",
        ]
    )
    if result.get("warnings"):
        lines.append("")
        lines.append("Warnings:")
        for w in result["warnings"][:24]:
            lines.append(f"  {w}")
    if result.get("failures"):
        lines.append("")
        lines.append("Failures:")
        for f in result["failures"][:24]:
            lines.append(f"  {f}")
    return "\n".join(lines) + "\n"
