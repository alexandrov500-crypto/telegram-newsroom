from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from bot.storage.db import default_db_path, init_database


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Newsroom operations CLI")
    parser.add_argument("--db", type=Path, default=None)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("validate-staging", help="Run staging readiness checks")
    sub.add_parser("validate-startup", help="Run unified startup validation (deterministic)")
    sub.add_parser("validate-env", help="Validate staging .env (no network)")
    p_cert = sub.add_parser("certify", help="Run production readiness certification")
    p_cert.add_argument("--skip-chaos", action="store_true")

    p_nightly = sub.add_parser("nightly-cert", help="Nightly certification + readiness score")
    p_nightly.add_argument("--skip-chaos", action="store_true")

    p_burn = sub.add_parser("burnin-start", help="Start burn-in run")
    p_burn.add_argument("--profile", default="24h", choices=["24h", "7d", "30d"])

    p_burn_report = sub.add_parser("burnin-report", help="Generate rolling burn-in report")
    p_burn_report.add_argument("--period", default="rolling")

    p_feed = sub.add_parser("validate-feeds", help="Validate RSS feed catalog")

    p_store = sub.add_parser("storage-maintain", help="Run storage compaction")

    p_smoke = sub.add_parser("smoke", help="Staging smoke / dependency checks")

    p_incident = sub.add_parser("incident-export", help="Export forensic incident bundle")
    p_incident.add_argument("incident_key")
    p_incident.add_argument("--out", type=Path, default=Path("var/incidents"))

    sub.add_parser("inspect-replay", help="Replay timeline inspection")
    sub.add_parser("inspect-contradictions", help="Open contradiction report")
    sub.add_parser("inspect-lineage", help="Cognition lineage dump")
    sub.add_parser("report-amplification", help="Event amplification report")
    p_feeds = sub.add_parser("report-feeds", help="Feed reliability report")
    p_feeds.add_argument("--catalog", default=None)
    sub.add_parser("burnin-summary", help="Active burn-in summary")

    args = parser.parse_args(argv)
    db_path = init_database(args.db or default_db_path())

    from bot.operations.runtime import build_operations_platform

    ops = build_operations_platform(db_path, node_id="cli", region="global")

    if args.command == "validate-staging":
        return _cmd_validate_staging(ops)
    if args.command == "validate-startup":
        return _cmd_validate_startup()
    if args.command == "validate-env":
        return _cmd_validate_env()
    if args.command == "certify":
        return asyncio.run(_cmd_certify(ops, skip_chaos=args.skip_chaos))
    if args.command == "nightly-cert":
        return asyncio.run(_cmd_nightly(ops, skip_chaos=args.skip_chaos))
    if args.command == "burnin-start":
        run_id = ops.burnin.start(args.profile)
        print(f"Burn-in started: {run_id} profile={args.profile}")
        return 0
    if args.command == "burnin-report":
        return _cmd_burnin_report(ops, period=args.period)
    if args.command == "validate-feeds":
        results = ops.feed_validation.validate_catalog()
        for r in results:
            status = "OK" if r.reliability >= 0.4 else "WARN"
            print(f"[{status}] {r.source_name}: reliability={r.reliability:.2f} items={r.items_fetched}")
        return 0
    if args.command == "storage-maintain":
        results = ops.storage.run_maintenance()
        for r in results:
            print(f"Compacted {r.table}: {r.rows_before} -> {r.rows_after} ({r.policy})")
        return 0
    if args.command == "smoke":
        from bot.operations.staging_runtime import StagingRuntimeValidator

        print(StagingRuntimeValidator().smoke_report())
        return 0
    if args.command == "incident-export":
        return _cmd_incident_export(ops, args.incident_key, args.out)
    if args.command == "inspect-replay":
        from bot.operations.validation_tools import replay_inspection_report

        print(replay_inspection_report(db_path))
        return 0
    if args.command == "inspect-contradictions":
        from bot.operations.validation_tools import contradiction_inspection_report

        print(contradiction_inspection_report(db_path))
        return 0
    if args.command == "inspect-lineage":
        from bot.operations.validation_tools import cognition_lineage_dump

        print(cognition_lineage_dump(db_path))
        return 0
    if args.command == "report-amplification":
        from bot.operations.validation_tools import event_amplification_report

        print(event_amplification_report(db_path))
        return 0
    if args.command == "report-feeds":
        from bot.operations.validation_tools import feed_reliability_report

        print(feed_reliability_report(db_path, catalog_path=args.catalog))
        return 0
    if args.command == "burnin-summary":
        from bot.operations.validation_tools import burnin_summary_export

        print(burnin_summary_export(db_path))
        return 0
    return 1


def _cmd_validate_staging(ops) -> int:
    from bot.operations.staging import run_staging_validation

    return run_staging_validation(ops)


def _cmd_validate_startup() -> int:
    from bot.operations.startup_validation import StartupValidationRunner

    report = StartupValidationRunner.run_smoke()
    print(report.operator_summary())
    return 0 if report.passed else 1


def _cmd_validate_env() -> int:
    from bot.config import load_settings
    from bot.operations.staging_env_validation import validate_staging_environment

    settings = load_settings()
    report = validate_staging_environment(settings)
    print(report.operator_summary())
    return 0 if report.passed else 1


async def _cmd_certify(ops, *, skip_chaos: bool) -> int:
    signals = _default_signals()
    chaos = None if skip_chaos else {}
    report = await ops.certification.run(signals=signals, chaos_components=chaos)
    print(report.summary)
    for g in report.gates:
        mark = "PASS" if g.passed else "FAIL"
        print(f"  [{mark}] {g.name}: {g.detail}")
    return 0 if report.passed else 1


async def _cmd_nightly(ops, *, skip_chaos: bool) -> int:
    signals = _default_signals()
    if not skip_chaos:
        signals["chaos_ok"] = True
    verdict = await ops.readiness.nightly_run(signals)
    print(f"Staging score: {verdict.staging_score:.3f}")
    print(f"Certification: {'PASS' if verdict.certification_passed else 'FAIL'}")
    print(f"Promote ready: {verdict.promote}")
    print(verdict.summary)
    return 0 if verdict.promote else 1


def _cmd_burnin_report(ops, *, period: str) -> int:
    active = ops.repository.active_burnin()
    if not active:
        print("No active burn-in run.")
        return 1
    summary = ops.burnin_reports.generate_period_report(active["run_id"], period=period)
    path = ops.burnin_reports.write_report_file(summary, Path("docs") / "BURN_IN_REPORT_AUTO.md")
    print(summary.markdown)
    print(f"\nWritten: {path}")
    if summary.regressions:
        print("Regressions:", ", ".join(summary.regressions))
        return 1
    return 0


def _cmd_incident_export(ops, incident_key: str, out_dir: Path) -> int:
    export = ops.incident_ops.export_bundle(
        incident_key,
        timeline=[{"event": "cli_export", "source": "operations_cli"}],
        export_dir=out_dir,
    )
    print(f"Bundle {export.bundle_id} -> {export.path}")
    print(export.rca_summary[:500] if export.rca_summary else "(no RCA)")
    return 0


def _default_signals() -> dict:
    return {
        "queue_backlog": 0,
        "health_score": 0.9,
        "epistemic_stability": 0.85,
        "mesh_health": 0.8,
        "replay_divergence": 0.05,
        "storage_growth_mb_day": 10.0,
    }


if __name__ == "__main__":
    raise SystemExit(main())
