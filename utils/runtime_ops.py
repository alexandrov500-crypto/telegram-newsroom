"""Thin deterministic runner for operational tooling steps (no orchestrator, no daemon)."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, Literal

StepStatus = Literal["OK", "WARNING", "FAIL", "SKIPPED"]

NIGHTLY_STEP_ORDER: tuple[str, ...] = (
    "preflight",
    "benchmark",
    "soak",
    "bundle",
    "regression",
    "qualification",
    "dashboard",
    "retention",
)

ALL_COMMANDS: tuple[str, ...] = (
    "benchmark",
    "bundle",
    "dashboard",
    "nightly-check",
    "preflight",
    "qualification",
    "regression",
    "retention",
    "soak",
)


def _load_tool_module(module_name: str, relative_path: str) -> Any:
    root = Path(__file__).resolve().parents[1]
    path = root / relative_path
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@dataclass
class RuntimeOpsContext:
    """Paths and flags for one ops invocation."""

    output_dir: Path
    runtime_dir: Path | None = None
    artifacts_dir: Path | None = None
    reports_dir: Path | None = None
    baseline: Path | None = None
    dry_run: bool = False
    strict: bool = False
    short_soak: bool = False
    skip_retention: bool = False
    settings: Any | None = None
    settings_factory: Callable[[], Any] | None = None


@dataclass
class StepResult:
    name: str
    status: StepStatus
    exit_code: int = 0
    warnings: list[str] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)


def _resolve(p: Path | None) -> Path | None:
    if p is None:
        return None
    return p.expanduser().resolve()


def _load_settings(ctx: RuntimeOpsContext) -> Any:
    if ctx.settings is not None:
        return ctx.settings
    if ctx.settings_factory is not None:
        return ctx.settings_factory()
    from app.config import load_settings

    return load_settings()


def _worst_step(a: StepStatus, b: StepStatus) -> StepStatus:
    ra = {"FAIL": 3, "WARNING": 2, "OK": 1, "SKIPPED": 0}.get(a, 0)
    rb = {"FAIL": 3, "WARNING": 2, "OK": 1, "SKIPPED": 0}.get(b, 0)
    return a if ra >= rb else b


def run_preflight_step(ctx: RuntimeOpsContext) -> StepResult:
    from utils.runtime_preflight import evaluate_preflight

    settings = None
    err: str | None = None
    try:
        settings = _load_settings(ctx)
    except Exception as exc:
        err = repr(exc)
    rd, ad, repd = _resolve(ctx.runtime_dir), _resolve(ctx.artifacts_dir), _resolve(ctx.reports_dir)
    report = evaluate_preflight(
        runtime_dir=rd,
        artifacts_dir=ad,
        reports_dir=repd,
        settings=settings,
        settings_load_error=err,
        check_redis=False,
        check_disk_space=False,
        min_free_mb=100.0,
    )
    st = str(report.get("overall_status") or "OK")
    status: StepStatus = "FAIL" if st == "FAIL" else ("WARNING" if st == "WARNING" else "OK")
    code = 1 if status == "FAIL" else 0
    return StepResult(
        name="preflight",
        status=status,
        exit_code=code,
        warnings=list(report.get("flat_messages") or []),
    )


def run_benchmark_step(ctx: RuntimeOpsContext) -> StepResult:
    if ctx.dry_run:
        return StepResult("benchmark", "SKIPPED", 0, warnings=["dry_run:skipped"])
    rd = _resolve(ctx.runtime_dir)
    if rd is None or not rd.is_dir():
        return StepResult("benchmark", "FAIL", 1, warnings=["benchmark:runtime_dir_invalid"])
    try:
        rb_mod = _load_tool_module("_runtime_benchmark_ops", "tools/runtime_benchmark.py")
        settings = replace(_load_settings(ctx), runtime_state_dir=str(rd))
        out = asyncio.run(rb_mod.async_main(settings, sample_transport=False))
    except Exception as exc:
        return StepResult("benchmark", "FAIL", 1, warnings=[f"benchmark:{exc!r}"])
    outp = _resolve(ctx.output_dir) / "ops_benchmark.json"
    try:
        outp.parent.mkdir(parents=True, exist_ok=True)
        outp.write_text(json.dumps(out, indent=2, sort_keys=True, default=str), encoding="utf-8")
    except OSError as exc:
        return StepResult("benchmark", "WARNING", 0, warnings=[f"benchmark_write:{exc!r}"], artifacts=[])
    return StepResult("benchmark", "OK", 0, artifacts=[str(outp)])


def run_soak_step(ctx: RuntimeOpsContext) -> StepResult:
    if ctx.dry_run:
        return StepResult("soak", "SKIPPED", 0, warnings=["dry_run:skipped"])
    rd = _resolve(ctx.runtime_dir)
    if rd is None or not rd.is_dir():
        return StepResult("soak", "FAIL", 1, warnings=["soak:runtime_dir_invalid"])
    try:
        from utils.soak_simulation import soak_result_to_dict, run_soak_simulation

        settings = replace(_load_settings(ctx), runtime_state_dir=str(rd))
        max_ticks = 12 if ctx.short_soak else None
        dur = 0.15 if ctx.short_soak else 0.2
        result = asyncio.run(
            run_soak_simulation(
                settings,
                "low",
                duration_sec=dur,
                tick_interval_sec=0.02,
                max_ticks=max_ticks,
                reset_metrics_at_start=True,
            ),
        )
        full = soak_result_to_dict(result)
        sj = rd / "soak_report.json"
        sj.write_text(json.dumps(full, indent=2, sort_keys=True, default=str), encoding="utf-8")
    except Exception as exc:
        return StepResult("soak", "FAIL", 1, warnings=[f"soak:{exc!r}"])
    st: StepStatus = "OK" if bool(result.bounded_report.get("ok")) else "WARNING"
    return StepResult(
        "soak",
        st,
        0 if st == "OK" else 1,
        artifacts=[str(sj)],
        warnings=list(full.get("warnings") or [])[:24],
    )


def run_bundle_step(ctx: RuntimeOpsContext) -> StepResult:
    if ctx.dry_run:
        return StepResult("bundle", "SKIPPED", 0, warnings=["dry_run:skipped"])
    rd = _resolve(ctx.runtime_dir)
    od = _resolve(ctx.output_dir)
    if rd is None or not rd.is_dir() or od is None:
        return StepResult("bundle", "FAIL", 1, warnings=["bundle:paths_invalid"])
    try:
        from utils.runtime_bundle import write_runtime_bundle

        settings = replace(_load_settings(ctx), runtime_state_dir=str(rd))
        zip_path = od / "runtime_bundle.zip"
        write_runtime_bundle(
            rd,
            zip_path,
            settings,
            include_html=False,
            fail_on_missing=False,
            metadata=None,
        )
    except Exception as exc:
        return StepResult("bundle", "FAIL", 1, warnings=[f"bundle:{exc!r}"])
    return StepResult("bundle", "OK", 0, artifacts=[str(od / "runtime_bundle.zip")])


def run_regression_step(ctx: RuntimeOpsContext) -> StepResult:
    if ctx.dry_run:
        return StepResult("regression", "SKIPPED", 0, warnings=["dry_run:skipped"])
    bl = _resolve(ctx.baseline)
    od = _resolve(ctx.output_dir)
    cur = od / "runtime_bundle.zip" if od else None
    if bl is None or cur is None or not cur.is_file():
        return StepResult(
            "regression",
            "SKIPPED",
            0,
            warnings=["regression:missing_baseline_or_bundle"],
        )
    try:
        from utils.runtime_regression import run_regression_comparison

        raw = os.getenv("NEWSROOM_REGRESSION_SKIP_METRICS", "").strip()
        skip = frozenset(x.strip() for x in raw.split(",") if x.strip()) if raw else None
        payload, _code = run_regression_comparison(
            bl,
            cur,
            warn_pct=15.0,
            fail_pct=50.0,
            strict=False,
            ignore_missing=True,
            regression_skip_metrics=skip,
        )
    except Exception as exc:
        return StepResult("regression", "FAIL", 1, warnings=[f"regression:{exc!r}"])
    outp = od / "regression.json"
    outp.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    st = str(payload.get("overall_status") or "OK")
    status: StepStatus = "FAIL" if st == "FAIL" else ("WARNING" if st == "WARNING" else "OK")
    return StepResult("regression", status, 1 if status == "FAIL" else 0, artifacts=[str(outp)], warnings=list(payload.get("warnings") or [])[:32])


def run_qualification_step(ctx: RuntimeOpsContext) -> StepResult:
    if ctx.dry_run:
        return StepResult("qualification", "SKIPPED", 0, warnings=["dry_run:skipped"])
    bl = _resolve(ctx.baseline)
    od = _resolve(ctx.output_dir)
    cur = od / "runtime_bundle.zip" if od else None
    if bl is None or cur is None or not cur.is_file():
        return StepResult("qualification", "SKIPPED", 0, warnings=["qualification:missing_baseline_or_bundle"])
    try:
        from utils.release_qualification import evaluate_release_qualification

        rep, _code = evaluate_release_qualification(
            cur,
            bl,
            warn_pct=15.0,
            fail_pct=50.0,
            allow_warning=True,
            strict=False,
            require_soak=False,
            require_integrity_clean=True,
            require_regression_ok=False,
        )
    except Exception as exc:
        return StepResult("qualification", "FAIL", 1, warnings=[f"qualification:{exc!r}"])
    outp = od / "qualification.json"
    outp.write_text(json.dumps(rep, indent=2, sort_keys=True, default=str), encoding="utf-8")
    st = str(rep.get("qualification_status") or "OK")
    status: StepStatus = "FAIL" if st == "FAIL" else ("WARNING" if st == "WARNING" else "OK")
    return StepResult("qualification", status, 1 if status == "FAIL" else 0, artifacts=[str(outp)])


def run_dashboard_step(ctx: RuntimeOpsContext) -> StepResult:
    if ctx.dry_run:
        return StepResult("dashboard", "SKIPPED", 0, warnings=["dry_run:skipped"])
    od = _resolve(ctx.output_dir)
    if od is None:
        return StepResult("dashboard", "FAIL", 1, warnings=["dashboard:no_output_dir"])
    cur = od / "runtime_bundle.zip"
    qual_path = od / "qualification.json"
    reg = od / "regression.json"
    try:
        from utils.operational_dashboard import build_dashboard_payload, render_dashboard_html

        payload = build_dashboard_payload(
            runtime_bundle=cur if cur.is_file() else None,
            qualification_report=qual_path if qual_path.is_file() else None,
            regression_report=reg if reg.is_file() else None,
            retention_report=None,
            title="Runtime ops dashboard",
        )
        html = render_dashboard_html(payload, include_json_snippets=False)
        outp = od / "operational_dashboard.html"
        outp.write_text(html, encoding="utf-8")
    except Exception as exc:
        return StepResult("dashboard", "FAIL", 1, warnings=[f"dashboard:{exc!r}"])
    return StepResult("dashboard", "OK", 0, artifacts=[str(outp)])


def run_retention_step(ctx: RuntimeOpsContext) -> StepResult:
    if ctx.dry_run or ctx.skip_retention:
        return StepResult(
            "retention",
            "SKIPPED",
            0,
            warnings=["dry_run:skipped"] if ctx.dry_run else ["skip_retention:true"],
        )
    od = _resolve(ctx.output_dir)
    if od is None:
        return StepResult("retention", "SKIPPED", 0, warnings=["retention:no_output_dir"])
    try:
        from utils.runtime_retention import run_retention_pass

        rep = run_retention_pass(
            artifacts_dir=od,
            baselines_dir=None,
            reports_dir=_resolve(ctx.reports_dir),
            retain_count=50,
            max_age_days=0.0,
            include_html=False,
            dry_run=False,
        )
        outp = od / "retention.json"
        outp.write_text(json.dumps(rep, indent=2, sort_keys=True, default=str), encoding="utf-8")
    except Exception as exc:
        return StepResult("retention", "WARNING", 0, warnings=[f"retention:{exc!r}"])
    return StepResult("retention", "OK", 0, artifacts=[str(outp)])


def _step_to_dict(r: StepResult) -> dict[str, Any]:
    return {
        "artifacts": sorted(r.artifacts),
        "exit_code": int(r.exit_code),
        "name": r.name,
        "status": r.status,
        "warnings": sorted(r.warnings),
    }


def run_nightly_check(ctx: RuntimeOpsContext) -> dict[str, Any]:
    """Sequential nightly pipeline (bounded, same-process)."""
    wall0 = time.monotonic()
    t0 = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    steps: list[StepResult] = []
    od = _resolve(ctx.output_dir)
    if od is not None:
        od.mkdir(parents=True, exist_ok=True)

    for name in NIGHTLY_STEP_ORDER:
        if name == "retention" and ctx.skip_retention:
            steps.append(StepResult("retention", "SKIPPED", 0, warnings=["skip_retention"]))
            continue
        fn = {
            "preflight": run_preflight_step,
            "benchmark": run_benchmark_step,
            "soak": run_soak_step,
            "bundle": run_bundle_step,
            "regression": run_regression_step,
            "qualification": run_qualification_step,
            "dashboard": run_dashboard_step,
            "retention": run_retention_step,
        }[name]
        steps.append(fn(ctx))

    t1 = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    executed = [s.name for s in steps if s.status != "SKIPPED"]
    skipped = [s.name for s in steps if s.status == "SKIPPED"]
    warnings = sorted({w for s in steps for w in s.warnings})
    arts = sorted({a for s in steps for a in s.artifacts})
    overall: StepStatus = "OK"
    for s in steps:
        overall = _worst_step(overall, s.status)
    fail_any = any(s.status == "FAIL" for s in steps)
    ok = not fail_any
    if ctx.strict:
        ok = ok and all(s.status in ("OK", "SKIPPED") for s in steps)
    status_line = "FAIL" if fail_any else ("WARNING" if overall == "WARNING" else "OK")
    report: dict[str, Any] = {
        "command": "nightly-check",
        "completed_at": t1,
        "executed_steps": executed,
        "generated_artifacts": arts,
        "ok": ok,
        "preflight_ok": ok,
        "skipped_steps": skipped,
        "started_at": t0,
        "status": status_line,
        "steps": [_step_to_dict(s) for s in steps],
        "warnings": warnings,
    }
    if od is not None:
        try:
            from observability.health_snapshot import (
                HealthSnapshotInputs,
                build_health_snapshot_from_inputs,
                default_health_snapshot_path,
                write_health_snapshot,
            )

            snap = build_health_snapshot_from_inputs(
                HealthSnapshotInputs(
                    ops_report=report,
                    output_dir=od,
                    runtime_duration_sec=round(time.monotonic() - wall0, 3),
                ),
            )
            snap_path = write_health_snapshot(default_health_snapshot_path(od), snap)
            arts = sorted(set(arts) | {str(snap_path)})
            report["generated_artifacts"] = arts
            report["health_snapshot_path"] = str(snap_path)

            from observability.runtime_report import (
                RuntimeReportInputs,
                build_runtime_report_from_inputs,
                default_runtime_report_path,
                write_runtime_report,
            )

            rpt = build_runtime_report_from_inputs(
                RuntimeReportInputs(
                    ops_report=report,
                    output_dir=od,
                    health_snapshot=snap,
                    health_snapshot_path=snap_path,
                ),
            )
            rpt_path = write_runtime_report(default_runtime_report_path(od), rpt)
            arts = sorted(set(arts) | {str(rpt_path)})
            report["generated_artifacts"] = arts
            report["runtime_report_path"] = str(rpt_path)

            from observability.runtime_manifest import (
                build_runtime_manifest,
                default_runtime_manifest_path,
                write_runtime_manifest,
            )

            qual_doc = None
            qp = od / "qualification.json"
            if qp.is_file():
                try:
                    qual_doc = json.loads(qp.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    qual_doc = None
            manifest = build_runtime_manifest(
                output_dir=od,
                ops_report=report,
                qualification=qual_doc,
            )
            man_path = write_runtime_manifest(default_runtime_manifest_path(od), manifest)
            arts = sorted(set(arts) | {str(man_path)})
            report["generated_artifacts"] = arts
            report["runtime_manifest_path"] = str(man_path)

            from observability.runtime_recovery import (
                default_recovery_report_path,
                validate_runtime_recovery,
                write_recovery_report,
            )

            recovery = validate_runtime_recovery(od)
            rec_path = write_recovery_report(default_recovery_report_path(od), recovery)
            arts = sorted(set(arts) | {str(rec_path)})
            report["generated_artifacts"] = arts
            report["recovery_report_path"] = str(rec_path)

            from observability.runtime_schema import (
                build_compatibility_report,
                default_compatibility_report_path,
                write_compatibility_report,
            )

            compat = build_compatibility_report(od)
            compat_path = write_compatibility_report(default_compatibility_report_path(od), compat)
            arts = sorted(set(arts) | {str(compat_path)})
            report["generated_artifacts"] = arts
            report["compatibility_report_path"] = str(compat_path)

            from observability.runtime_history import update_runtime_history

            hist_path, audit_path = update_runtime_history(
                od,
                recovery_report=recovery,
                compatibility_report=compat,
            )
            arts = sorted(set(arts) | {str(hist_path), str(audit_path)})
            report["generated_artifacts"] = arts
            report["qualification_history_path"] = str(hist_path)
            report["audit_snapshot_path"] = str(audit_path)

            from observability.runtime_baseline import compare_and_write_drift

            drift, drift_path = compare_and_write_drift(od)
            arts = sorted(set(arts) | {str(drift_path)})
            report["generated_artifacts"] = arts
            report["drift_report_path"] = str(drift_path)
            report["drift_status"] = drift.get("drift_status")

            from observability.runtime_capabilities import update_runtime_capabilities

            cap_prof_path, cap_rep_path = update_runtime_capabilities(od)
            arts = sorted(set(arts) | {str(cap_prof_path), str(cap_rep_path)})
            report["generated_artifacts"] = arts
            report["runtime_capabilities_path"] = str(cap_prof_path)
            report["capability_report_path"] = str(cap_rep_path)

            from observability.runtime_policy import update_runtime_policy

            pol_path, pol_rep_path = update_runtime_policy(od)
            arts = sorted(set(arts) | {str(pol_path), str(pol_rep_path)})
            report["generated_artifacts"] = arts
            report["runtime_policy_path"] = str(pol_path)
            report["policy_report_path"] = str(pol_rep_path)

            from observability.runtime_index import update_runtime_index

            idx_path = update_runtime_index(od)
            arts = sorted(set(arts) | {str(idx_path)})
            report["generated_artifacts"] = arts
            report["runtime_index_path"] = str(idx_path)
        except Exception as exc:
            warnings = sorted(set(warnings) | {f"health_snapshot:{exc!r}"})
            report["warnings"] = warnings
    return report


def run_single_command(command: str, ctx: RuntimeOpsContext) -> dict[str, Any]:
    t0 = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    fn = {
        "preflight": run_preflight_step,
        "benchmark": run_benchmark_step,
        "soak": run_soak_step,
        "bundle": run_bundle_step,
        "regression": run_regression_step,
        "qualification": run_qualification_step,
        "dashboard": run_dashboard_step,
        "retention": run_retention_step,
    }.get(command)
    if fn is None:
        return {
            "command": command,
            "completed_at": t0,
            "error": "unknown_command",
            "executed_steps": [],
            "generated_artifacts": [],
            "ok": False,
            "preflight_ok": False,
            "skipped_steps": [],
            "started_at": t0,
            "status": "FAIL",
            "steps": [],
            "warnings": [],
        }
    r = fn(ctx)
    t1 = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    fail = r.status == "FAIL"
    ok = not fail and (not ctx.strict or r.status in ("OK", "SKIPPED"))
    return {
        "command": command,
        "completed_at": t1,
        "executed_steps": [command] if r.status != "SKIPPED" else [],
        "generated_artifacts": sorted(r.artifacts),
        "ok": ok,
        "preflight_ok": ok,
        "skipped_steps": [command] if r.status == "SKIPPED" else [],
        "started_at": t0,
        "status": r.status,
        "steps": [_step_to_dict(r)],
        "warnings": sorted(r.warnings),
    }


def render_runtime_ops_summary(report: dict[str, Any]) -> str:
    cmd = str(report.get("command") or "ops")
    lines = [
        "Runtime ops summary",
        "",
        f"Command: {cmd}",
        "",
    ]
    for block in report.get("steps") or []:
        name = str(block.get("name") or "?")
        st = str(block.get("status") or "UNKNOWN").upper()
        badge = "[OK]" if st == "OK" else ("[WARNING]" if st == "WARNING" else ("[FAIL]" if st == "FAIL" else "[SKIPPED]"))
        lines.append(f"{badge} {name}")
    lines.extend(["", f"Overall: {report.get('status', 'UNKNOWN')}"])
    if report.get("warnings"):
        lines.append("")
        lines.append("Warnings:")
        for w in report["warnings"][:20]:
            lines.append(f"  {w}")
    return "\n".join(lines) + "\n"


def ops_exit_code(report: dict[str, Any], *, strict: bool) -> int:
    if not report.get("ok", False):
        return 1
    if strict and str(report.get("status")) != "OK":
        return 1
    return 0
