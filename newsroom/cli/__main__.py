#!/usr/bin/env python3
"""``python -m newsroom.cli health`` — offline health snapshot and runtime report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _resolve_output_dir(path: Path | None) -> Path:
    if path is not None:
        p = path.expanduser().resolve()
        if p.is_file():
            if p.name in (
                "health_snapshot.json",
                "runtime_report.json",
                "runtime_manifest.json",
                "recovery_report.json",
                "compatibility_report.json",
                "qualification_history.json",
                "audit_snapshot.json",
                "runtime_baseline.json",
                "drift_report.json",
                "runtime_capabilities.json",
                "capability_report.json",
                "runtime_policy.json",
                "policy_report.json",
                "runtime_index.json",
            ):
                return p.parent.parent
            return p.parent
        return p
    return (Path.cwd() / "runtime_ops_output").resolve()


def _cmd_health(argv: list[str] | None) -> int:
    from observability.health_snapshot import (
        default_health_snapshot_path,
        load_health_snapshot,
        render_health_summary,
    )
    from observability.runtime_report import (
        default_runtime_report_path,
        load_runtime_report,
        render_runtime_report_summary,
        strict_report_exit_code,
    )

    p = argparse.ArgumentParser(description="Runtime health snapshot and report (offline JSON)")
    p.add_argument(
        "--path",
        type=Path,
        default=None,
        help="output directory or health_snapshot.json / runtime_report.json",
    )
    p.add_argument(
        "--json", action="store_true", help="Print JSON (health or report when --report)"
    )
    p.add_argument(
        "--report", action="store_true", help="Show runtime report summary instead of health"
    )
    p.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero when runtime report incident_level is not NONE",
    )
    args = p.parse_args(argv)

    out_dir = _resolve_output_dir(args.path)
    code = 0

    if args.report:
        rpt_path = default_runtime_report_path(out_dir)
        if args.path and args.path.expanduser().resolve().is_file():
            name = args.path.expanduser().resolve().name
            if name == "runtime_report.json":
                rpt_path = args.path.expanduser().resolve()
        rpt = load_runtime_report(rpt_path)
        if rpt is None:
            print(f"error: runtime report not found: {rpt_path}", file=sys.stderr)
            return 1
        if args.json:
            sys.stdout.write(json.dumps(rpt, indent=2, sort_keys=True, default=str) + "\n")
        else:
            sys.stdout.write(render_runtime_report_summary(rpt))
        if args.strict:
            code = strict_report_exit_code(rpt)
    else:
        snap_path = default_health_snapshot_path(out_dir)
        if args.path and args.path.expanduser().resolve().is_file():
            if args.path.expanduser().resolve().name == "health_snapshot.json":
                snap_path = args.path.expanduser().resolve()
        snap = load_health_snapshot(snap_path)
        if snap is None:
            print(f"error: snapshot not found: {snap_path}", file=sys.stderr)
            return 1
        if args.json:
            sys.stdout.write(json.dumps(snap, indent=2, sort_keys=True, default=str) + "\n")
        else:
            sys.stdout.write(render_health_summary(snap))
        if args.strict:
            rpt = load_runtime_report(default_runtime_report_path(out_dir))
            if rpt is None:
                print("error: --strict requires runtime/runtime_report.json", file=sys.stderr)
                return 1
            code = strict_report_exit_code(rpt)

    return code


def _cmd_verify_runtime(argv: list[str] | None) -> int:
    from observability.runtime_manifest import default_runtime_manifest_path
    from observability.runtime_verify import (
        render_verify_summary,
        strict_verify_exit_code,
        verify_runtime_manifest,
    )

    p = argparse.ArgumentParser(description="Offline runtime manifest and artifact verification")
    p.add_argument(
        "--path",
        type=Path,
        default=None,
        help="output directory or runtime_manifest.json",
    )
    p.add_argument("--json", action="store_true", help="Print verification JSON")
    p.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero on WARNING or FAIL",
    )
    args = p.parse_args(argv)

    out_dir = _resolve_output_dir(args.path)
    man_path = default_runtime_manifest_path(out_dir)
    if args.path and args.path.expanduser().resolve().is_file():
        if args.path.expanduser().resolve().name == "runtime_manifest.json":
            man_path = args.path.expanduser().resolve()

    result = verify_runtime_manifest(output_dir=out_dir, manifest_path=man_path)
    if args.json:
        sys.stdout.write(json.dumps(result, indent=2, sort_keys=True, default=str) + "\n")
    else:
        sys.stdout.write(render_verify_summary(result))
    return strict_verify_exit_code(result, strict=args.strict)


def health_main(argv: list[str] | None = None) -> int:
    """Entry point for ``newsroom-health`` console script."""
    return _cmd_health(argv)


def verify_runtime_main(argv: list[str] | None = None) -> int:
    """Entry point for ``newsroom-verify-runtime`` console script."""
    return _cmd_verify_runtime(argv)


def _cmd_validate_recovery(argv: list[str] | None) -> int:
    from observability.runtime_recovery import (
        default_recovery_report_path,
        render_recovery_summary,
        strict_recovery_exit_code,
        validate_runtime_recovery,
        write_recovery_report,
    )

    p = argparse.ArgumentParser(description="Offline runtime recovery validation")
    p.add_argument(
        "--path",
        type=Path,
        default=None,
        help="output directory or recovery_report.json",
    )
    p.add_argument("--json", action="store_true", help="Print recovery report JSON")
    p.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero on WARNING or FAIL",
    )
    p.add_argument(
        "--write",
        action="store_true",
        help="Write runtime/recovery_report.json (latest-only)",
    )
    args = p.parse_args(argv)

    out_dir = _resolve_output_dir(args.path)
    report = validate_runtime_recovery(out_dir)
    if args.write:
        write_recovery_report(default_recovery_report_path(out_dir), report)
    if args.json:
        sys.stdout.write(json.dumps(report, indent=2, sort_keys=True, default=str) + "\n")
    else:
        sys.stdout.write(render_recovery_summary(report))
    return strict_recovery_exit_code(report, strict=args.strict)


def _cmd_replay_runtime(argv: list[str] | None) -> int:
    from newsroom.cli.inspection_common import emit_json, strict_tri_state_exit

    from observability.runtime_recovery import render_replay_summary, replay_runtime_inspection

    p = argparse.ArgumentParser(
        description="Inspection-only runtime replay (extract bundle to temp, verify, no pipeline)",
    )
    from newsroom.cli.inspection_common import add_standard_inspection_args

    add_standard_inspection_args(p)
    args = p.parse_args(argv)

    out_dir = _resolve_output_dir(args.path)
    result = replay_runtime_inspection(out_dir)
    if args.json:
        emit_json(result)
    else:
        sys.stdout.write(render_replay_summary(result))
    return strict_tri_state_exit(str(result.get("recovery_status") or "FAIL"), strict=args.strict)


def validate_recovery_main(argv: list[str] | None = None) -> int:
    """Entry point for ``newsroom-validate-recovery`` console script."""
    return _cmd_validate_recovery(argv)


def replay_runtime_main(argv: list[str] | None = None) -> int:
    """Entry point for ``newsroom-replay-runtime`` console script."""
    return _cmd_replay_runtime(argv)


def _cmd_check_compatibility(argv: list[str] | None) -> int:
    from observability.runtime_schema import (
        build_compatibility_report,
        default_compatibility_report_path,
        render_compatibility_summary,
        strict_compatibility_exit_code,
        write_compatibility_report,
    )

    p = argparse.ArgumentParser(description="Offline runtime schema compatibility check")
    p.add_argument(
        "--path",
        type=Path,
        default=None,
        help="output directory or compatibility_report.json",
    )
    p.add_argument("--json", action="store_true", help="Print compatibility report JSON")
    p.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero on WARNING or FAIL",
    )
    p.add_argument(
        "--write",
        action="store_true",
        help="Write runtime/compatibility_report.json (latest-only)",
    )
    args = p.parse_args(argv)

    out_dir = _resolve_output_dir(args.path)
    report = build_compatibility_report(out_dir)
    if args.write:
        write_compatibility_report(default_compatibility_report_path(out_dir), report)
    if args.json:
        sys.stdout.write(json.dumps(report, indent=2, sort_keys=True, default=str) + "\n")
    else:
        sys.stdout.write(render_compatibility_summary(report))
    return strict_compatibility_exit_code(report, strict=args.strict)


def check_compatibility_main(argv: list[str] | None = None) -> int:
    """Entry point for ``newsroom-check-compatibility`` console script."""
    return _cmd_check_compatibility(argv)


def _cmd_audit_runtime(argv: list[str] | None) -> int:
    from observability.runtime_history import (
        default_audit_snapshot_path,
        default_qualification_history_path,
        load_qualification_history,
        render_audit_summary,
        strict_audit_exit_code,
    )

    p = argparse.ArgumentParser(
        description="Bounded runtime qualification history and audit summary"
    )
    p.add_argument(
        "--path",
        type=Path,
        default=None,
        help="output directory or audit_snapshot.json",
    )
    p.add_argument("--json", action="store_true", help="Print audit snapshot JSON")
    p.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero when latest qualification or audit status is not OK",
    )
    args = p.parse_args(argv)

    out_dir = _resolve_output_dir(args.path)
    audit_path = default_audit_snapshot_path(out_dir)
    if args.path and args.path.expanduser().resolve().is_file():
        if args.path.expanduser().resolve().name == "audit_snapshot.json":
            audit_path = args.path.expanduser().resolve()

    hist = load_qualification_history(default_qualification_history_path(out_dir))
    snap_doc = None
    if audit_path.is_file():
        try:
            snap_doc = json.loads(audit_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            snap_doc = None
    if snap_doc is None:
        from observability.runtime_history import build_audit_snapshot, write_audit_snapshot

        snap_doc = build_audit_snapshot(out_dir, history=hist)
        write_audit_snapshot(audit_path, snap_doc)

    if args.json:
        payload = {"audit_snapshot": snap_doc, "qualification_history": hist}
        sys.stdout.write(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n")
    else:
        sys.stdout.write(render_audit_summary(snap_doc, hist))
    return strict_audit_exit_code(snap_doc, strict=args.strict)


def audit_runtime_main(argv: list[str] | None = None) -> int:
    """Entry point for ``newsroom-audit-runtime`` console script."""
    return _cmd_audit_runtime(argv)


def _cmd_create_baseline(argv: list[str] | None) -> int:
    from observability.runtime_baseline import create_runtime_baseline

    p = argparse.ArgumentParser(description="Snapshot current runtime state as baseline")
    p.add_argument("--path", type=Path, default=None, help="ops output directory")
    p.add_argument("--json", action="store_true", help="Print baseline JSON")
    args = p.parse_args(argv)

    out_dir = _resolve_output_dir(args.path)
    path = create_runtime_baseline(out_dir)
    baseline = json.loads(path.read_text(encoding="utf-8"))
    if args.json:
        sys.stdout.write(json.dumps(baseline, indent=2, sort_keys=True, default=str) + "\n")
    else:
        sys.stdout.write(f"Baseline written: {path}\n")
        sys.stdout.write(f"baseline_status: {baseline.get('baseline_status')}\n")
    return 0


def _cmd_compare_baseline(argv: list[str] | None) -> int:
    from observability.runtime_baseline import (
        compare_and_write_drift,
        render_drift_summary,
        strict_drift_exit_code,
    )

    p = argparse.ArgumentParser(description="Compare current runtime state against baseline")
    p.add_argument("--path", type=Path, default=None, help="ops output directory")
    p.add_argument("--json", action="store_true", help="Print drift report JSON")
    p.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero on WARNING or FAIL",
    )
    args = p.parse_args(argv)

    out_dir = _resolve_output_dir(args.path)
    report, _path = compare_and_write_drift(out_dir)
    if args.json:
        sys.stdout.write(json.dumps(report, indent=2, sort_keys=True, default=str) + "\n")
    else:
        sys.stdout.write(render_drift_summary(report))
    return strict_drift_exit_code(report, strict=args.strict)


def create_baseline_main(argv: list[str] | None = None) -> int:
    return _cmd_create_baseline(argv)


def compare_baseline_main(argv: list[str] | None = None) -> int:
    return _cmd_compare_baseline(argv)


def _cmd_inspect_capabilities(argv: list[str] | None) -> int:
    from observability.runtime_capabilities import (
        build_runtime_capability_profile,
        default_runtime_capabilities_path,
        load_runtime_capability_profile,
        render_capability_summary,
        strict_capability_exit_code,
        update_runtime_capabilities,
    )

    p = argparse.ArgumentParser(
        description="Inspect runtime capability profile and deployment semantics"
    )
    p.add_argument("--path", type=Path, default=None, help="ops output directory")
    p.add_argument("--json", action="store_true", help="Print profile and report JSON")
    p.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero on WARNING or FAIL",
    )
    p.add_argument(
        "--write",
        action="store_true",
        help="Write runtime_capabilities.json and capability_report.json",
    )
    p.add_argument(
        "--execution-mode",
        dest="execution_mode",
        default=None,
        help="Optional execution mode hint for validation (e.g. manual, systemd)",
    )
    args = p.parse_args(argv)

    out_dir = _resolve_output_dir(args.path)
    if args.write:
        prof_path, rep_path = update_runtime_capabilities(
            out_dir,
            execution_mode_hint=args.execution_mode,
        )
        profile = load_runtime_capability_profile(prof_path) or build_runtime_capability_profile(
            out_dir
        )
        report = json.loads(rep_path.read_text(encoding="utf-8"))
    else:
        profile = load_runtime_capability_profile(default_runtime_capabilities_path(out_dir))
        if profile is None:
            profile = build_runtime_capability_profile(
                out_dir,
                execution_mode_hint=args.execution_mode,
            )
        from observability.runtime_capabilities import build_capability_report

        report = build_capability_report(
            out_dir,
            profile=profile,
            execution_mode_hint=args.execution_mode,
        )

    if args.json:
        payload = {"runtime_capabilities": profile, "capability_report": report}
        sys.stdout.write(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n")
    else:
        sys.stdout.write(render_capability_summary(profile, report))
    return strict_capability_exit_code(report, strict=args.strict)


def inspect_capabilities_main(argv: list[str] | None = None) -> int:
    return _cmd_inspect_capabilities(argv)


def _cmd_inspect_policy(argv: list[str] | None) -> int:
    from observability.runtime_policy import (
        build_policy_report,
        build_runtime_policy,
        default_runtime_policy_path,
        load_runtime_policy,
        render_policy_summary,
        strict_policy_exit_code,
        update_runtime_policy,
    )

    p = argparse.ArgumentParser(description="Inspect runtime policies and operational guardrails")
    p.add_argument("--path", type=Path, default=None, help="ops output directory")
    p.add_argument("--json", action="store_true", help="Print policy and report JSON")
    p.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero on WARNING or FAIL",
    )
    p.add_argument(
        "--write",
        action="store_true",
        help="Write runtime_policy.json and policy_report.json",
    )
    args = p.parse_args(argv)

    out_dir = _resolve_output_dir(args.path)
    if args.write:
        pol_path, rep_path = update_runtime_policy(out_dir)
        policy = load_runtime_policy(pol_path) or build_runtime_policy(out_dir)
        report = json.loads(rep_path.read_text(encoding="utf-8"))
    else:
        policy = load_runtime_policy(default_runtime_policy_path(out_dir))
        if policy is None:
            policy = build_runtime_policy(out_dir)
        report = build_policy_report(out_dir, policy=policy)

    if args.json:
        payload = {"runtime_policy": policy, "policy_report": report}
        sys.stdout.write(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n")
    else:
        sys.stdout.write(render_policy_summary(policy, report))
    return strict_policy_exit_code(report, strict=args.strict)


def inspect_policy_main(argv: list[str] | None = None) -> int:
    return _cmd_inspect_policy(argv)


def _cmd_runtime_index(argv: list[str] | None) -> int:
    from observability.runtime_index import (
        build_runtime_index,
        default_runtime_index_path,
        load_runtime_index,
        render_index_summary,
        strict_index_exit_code,
        update_runtime_index,
        validate_runtime_index,
    )

    p = argparse.ArgumentParser(description="Unified runtime artifact index (inspection catalog)")
    p.add_argument("--path", type=Path, default=None, help="ops output directory")
    p.add_argument("--json", action="store_true", help="Print runtime index JSON")
    p.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero on WARNING or FAIL",
    )
    p.add_argument(
        "--write",
        action="store_true",
        help="Write runtime/runtime_index.json (latest-only)",
    )
    args = p.parse_args(argv)

    out_dir = _resolve_output_dir(args.path)
    if args.write:
        idx_path = update_runtime_index(out_dir)
        index = load_runtime_index(idx_path) or build_runtime_index(out_dir)
    else:
        index = load_runtime_index(default_runtime_index_path(out_dir))
        if index is None:
            index = build_runtime_index(out_dir)
        else:
            validation = validate_runtime_index(index, out_dir)
            index = dict(index)
            index["index_status"] = validation["index_validation_status"]

    if args.json:
        validation = validate_runtime_index(index, out_dir)
        payload = {"runtime_index": index, "validation": validation}
        sys.stdout.write(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n")
    else:
        sys.stdout.write(render_index_summary(index))
    return strict_index_exit_code(index, strict=args.strict)


def runtime_index_main(argv: list[str] | None = None) -> int:
    return _cmd_runtime_index(argv)


def _operator_commands() -> frozenset[str]:
    return frozenset(
        {
            "status",
            "logs",
            "diagnose",
            "takeover",
            "release",
            "queue",
            "drafts",
            "pipeline-run",
            "panel",
            "newsroom",
            "maintenance",
        }
    )


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    if not argv:
        return _cmd_health([])
    if argv[0] in ("-h", "--help"):
        print(
            "usage: python -m newsroom.cli {status|logs|health|verify-runtime|...} ...",
        )
        return 0
    if argv[0] in _operator_commands():
        from newsroom.cli.operator import main as operator_main

        return operator_main(argv)
    if argv[0] == "health":
        return _cmd_health(argv[1:])
    if argv[0] == "verify-runtime":
        return _cmd_verify_runtime(argv[1:])
    if argv[0] == "validate-recovery":
        return _cmd_validate_recovery(argv[1:])
    if argv[0] == "replay-runtime":
        return _cmd_replay_runtime(argv[1:])
    if argv[0] == "check-compatibility":
        return _cmd_check_compatibility(argv[1:])
    if argv[0] == "audit-runtime":
        return _cmd_audit_runtime(argv[1:])
    if argv[0] == "create-baseline":
        return _cmd_create_baseline(argv[1:])
    if argv[0] == "compare-baseline":
        return _cmd_compare_baseline(argv[1:])
    if argv[0] == "inspect-capabilities":
        return _cmd_inspect_capabilities(argv[1:])
    if argv[0] == "inspect-policy":
        return _cmd_inspect_policy(argv[1:])
    if argv[0] == "runtime-index":
        return _cmd_runtime_index(argv[1:])
    print(f"error: unknown command {argv[0]!r}", file=sys.stderr)
    print("hint: make runtime-help  |  python -m newsroom.cli health --help", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
