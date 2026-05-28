#!/usr/bin/env python3
"""Final PUBLIC GO readiness gate — PASS / CONDITIONAL / FAIL."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app.observability.burnin_eval import evaluate_readiness, fetch_tail_streak_rows, scan_log_contract
from app.observability.ops_health import gather_component_health
from app.observability.runtime_report import build_runtime_report
from app.observability.validation_contract import evaluate_release_contract, metric
from app.observability.validation_environment import detect_validation_environment, observational_policy
from utils.database_url import sqlite_path_from_url


def main() -> int:
    p = argparse.ArgumentParser(description="PUBLIC GO readiness check")
    p.add_argument("--json", action="store_true")
    p.add_argument("--min-burnin-days", type=int, default=3)
    args = p.parse_args()

    import sqlite3

    raw = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/newsroom.db").strip()
    path = sqlite_path_from_url(raw)
    required_checks: list[dict[str, str]] = []
    observational_checks: list[dict[str, str]] = []
    warnings: list[str] = []
    blockers: list[str] = []
    env_mode = detect_validation_environment()
    policy = observational_policy(env_mode)
    if not path or not Path(path).is_file():
        required_checks.extend(
            [
                metric("execution_graph_verdict", "UNKNOWN", reason="database_missing"),
                metric("publish_finalize_order_valid", "UNKNOWN", reason="database_missing"),
                metric("no_critical_runtime_events", "UNKNOWN", reason="database_missing"),
                metric("no_duplicate_publish_detected", "UNKNOWN", reason="database_missing"),
                metric("rollback_state_stable", "UNKNOWN", reason="database_missing"),
            ]
        )
        observational_checks.extend(
            [
                metric("publish_continuity_score", "UNKNOWN", reason="database_missing", kind="observational"),
                metric("telegram_health", "UNKNOWN", reason="database_missing", kind="observational"),
                metric("traffic_metrics", "UNKNOWN", reason="database_missing", kind="observational"),
                metric("latency_metrics", "UNKNOWN", reason="database_missing", kind="observational"),
                metric("engagement_proxy", "UNKNOWN", reason="database_missing", kind="observational"),
            ]
        )
        contract = evaluate_release_contract(
            source="public_go_check",
            required=required_checks,
            observational=observational_checks,
            ignore_missing_observational=bool(policy.get("ignore_missing_observational")),
        )
        blockers = list(contract.get("blockers") or [])
        verdict = "FAIL"
    else:
        conn = sqlite3.connect(path, timeout=5.0)
        tail = fetch_tail_streak_rows(conn, max_rows=10)
        ids = conn.execute(
            "SELECT id, finished_at FROM pipeline_ticks ORDER BY id DESC LIMIT 15"
        ).fetchall()
        from app.observability.burnin_eval import tail_consecutive_finished_streak

        streak = tail_consecutive_finished_streak([(int(i), f) for i, f in ids])
        log_path = Path(os.getenv("NEWSROOM_LOG", "logs/local-run.log"))
        log_scan = scan_log_contract(log_path)
        pub = __import__("app.observability.burnin_eval", fromlist=["publishability_metrics"]).publishability_metrics(
            conn
        )
        burn_verdict, burn_reasons = evaluate_readiness(
            tail_streak=tail,
            streak_count=streak,
            log_scan=log_scan,
            min_ticks=3,
            require_drafts_24h=1,
            publishability=pub,
        )
        conn.close()
        if int(log_scan.get("aborted_draft") or 0) > 0 or int(log_scan.get("pipeline_fatal_break") or 0) > 0:
            required_checks.append(metric("publish_finalize_order_valid", "FAIL", reason="fatal_or_aborted_logs"))
        else:
            required_checks.append(metric("publish_finalize_order_valid", "PASS"))
        if int(pub.get("running_ticks") or 0) > 0:
            warnings.append(f"unresolved_running_ticks:{pub['running_ticks']}")
            warnings.append("running_ticks_present")
        if int(pub.get("publishes_24h") or 0) < 1:
            warnings.append("no_publish_24h")
        if int(pub.get("committed_draft_24h") or 0) < 1:
            warnings.append("no_committed_draft_24h")

        health = gather_component_health()
        observational_checks.append(
            metric(
                "traffic_metrics",
                "PASS" if health.get("ok") else "FAIL",
                reason="" if health.get("ok") else "component_health_degraded",
                kind="observational",
            )
        )

        from pathlib import Path as _Path

        from app.observability.execution_graph_report import build_execution_graph_report

        runtime_dir = _Path(os.getenv("RUNTIME_STATE_DIR", "var/runtime"))
        eg = build_execution_graph_report(
            db_path=_Path(path) if path else None,
            runtime_dir=runtime_dir,
            log_path=log_path,
            window_ticks=100,
        )
        if eg.get("execution_graph_ready"):
            required_checks.append(metric("execution_graph_verdict", "PASS"))
        else:
            required_checks.append(
                metric(
                    "execution_graph_verdict",
                    "FAIL",
                    reason=(
                        f"consistency={eg.get('consistency_rate')} "
                        f"critical_per_100={eg.get('critical_anomalies_per_100_ticks')} "
                        f"warnings_per_100={eg.get('warning_anomalies_per_100_ticks')}"
                    ),
                )
            )

        from pathlib import Path as _P

        from app.observability.runtime_resilience_report import evaluate_public_go_resilience

        res_fails, res_warns = evaluate_public_go_resilience(_P(os.getenv("RUNTIME_STATE_DIR", "var/runtime")))
        if res_fails:
            required_checks.append(metric("rollback_state_stable", "FAIL", reason=";".join(res_fails)))
        else:
            required_checks.append(metric("rollback_state_stable", "PASS"))
        for w in res_warns:
            warnings.append(f"warn:{w}")

        dup_count = int(pub.get("duplicate_publish_violations") or 0)
        if dup_count > 0:
            required_checks.append(metric("no_duplicate_publish_detected", "FAIL", reason=f"duplicate={dup_count}"))
        else:
            required_checks.append(metric("no_duplicate_publish_detected", "PASS"))

        # Runtime critical from resilience/health perspective.
        if any("critical" in r for r in res_fails):
            required_checks.append(metric("no_critical_runtime_events", "FAIL", reason="runtime_critical_signals"))
        else:
            required_checks.append(metric("no_critical_runtime_events", "PASS"))

        try:
            report = build_runtime_report()
        except Exception as exc:
            report = {"runtime_report_error": repr(exc)[:200]}
        cont_score = ((report.get("publishability", {}) or {}).get("autonomous_continuity_score"))
        if cont_score is None:
            observational_checks.append(
                metric("publish_continuity_score", "UNKNOWN", reason="continuity_missing", kind="observational")
            )
        elif float(cont_score) < float(os.getenv("PUBLIC_GO_MIN_CONTINUITY_SCORE", "55")):
            observational_checks.append(
                metric("publish_continuity_score", "FAIL", reason=f"score={cont_score}", kind="observational")
            )
        else:
            observational_checks.append(metric("publish_continuity_score", "PASS", kind="observational"))

        observational_checks.append(metric("telegram_health", "UNKNOWN", reason="telegram_health_not_evaluated", kind="observational"))
        observational_checks.append(metric("latency_metrics", "UNKNOWN", reason="latency_not_evaluated", kind="observational"))
        observational_checks.append(metric("engagement_proxy", "UNKNOWN", reason="engagement_not_evaluated", kind="observational"))

        contract = evaluate_release_contract(
            source="public_go_check",
            required=required_checks,
            observational=observational_checks,
            ignore_missing_observational=bool(policy.get("ignore_missing_observational")),
        )
        blockers = list(contract.get("blockers") or [])
        blockers.extend(warnings)
        if contract.get("verdict") == "NOT_READY":
            verdict = "FAIL"
        elif contract.get("verdict") == "CONDITIONAL":
            verdict = "CONDITIONAL"
        else:
            verdict = "PASS"

    try:
        report = build_runtime_report()
    except Exception as exc:
        report = {"runtime_report_error": repr(exc)[:200], "publishability": {}, "health": {}}
    eg_summary: dict[str, object] = {}
    try:
        from pathlib import Path as _Path

        from app.observability.execution_graph_report import build_execution_graph_report

        eg_summary = build_execution_graph_report(
            db_path=_Path(path) if path and _Path(path).is_file() else None,
            runtime_dir=_Path(os.getenv("RUNTIME_STATE_DIR", "var/runtime")),
            log_path=_Path(os.getenv("NEWSROOM_LOG", "logs/local-run.log")),
            window_ticks=100,
        )
    except Exception:
        pass
    out = {
        "verdict": verdict,
        "blockers": sorted(set(blockers)),
        "validation_environment": env_mode,
        "required_checks": required_checks,
        "observational_checks": observational_checks,
        "min_burnin_days_required": args.min_burnin_days,
        "report_summary": {
            "publishes_24h": report.get("publishability", {}).get("publishes_24h"),
            "committed_draft_24h": report.get("publishability", {}).get("committed_draft_24h"),
            "health_ok": report.get("health", {}).get("ok"),
            "execution_graph_ready": eg_summary.get("execution_graph_ready"),
            "execution_graph_consistency": eg_summary.get("consistency_rate"),
        },
    }
    final_readiness: dict[str, object] = {}
    try:
        from pathlib import Path as _P

        from app.observability.public_readiness import evaluate_final_public_readiness

        final_readiness = evaluate_final_public_readiness(
            db_path=_P(path) if path and _P(path).is_file() else None,
            runtime_dir=_P(os.getenv("RUNTIME_STATE_DIR", "var/runtime")),
            log_path=_P(os.getenv("NEWSROOM_LOG", "logs/local-run.log")),
        )
        out["FINAL_PUBLIC_READINESS"] = final_readiness.get("FINAL_PUBLIC_READINESS")
        out["final_blockers"] = final_readiness.get("blockers")
        fr = str(final_readiness.get("FINAL_PUBLIC_READINESS") or "")
        if fr == "NOT_READY":
            verdict = "FAIL"
            blockers.extend(list(final_readiness.get("blockers") or []))
        elif fr == "CONDITIONAL" and verdict == "PASS":
            verdict = "CONDITIONAL"
    except Exception as exc:
        out["final_readiness_error"] = repr(exc)[:200]

    out["verdict"] = verdict
    out["blockers"] = sorted(set(blockers))

    if args.json:
        print(json.dumps(out, indent=2, ensure_ascii=False))
    else:
        print(f"PUBLIC GO: {verdict}")
        if final_readiness.get("FINAL_PUBLIC_READINESS"):
            print(f"FINAL_PUBLIC_READINESS: {final_readiness.get('FINAL_PUBLIC_READINESS')}")
        if blockers:
            print("Blockers:")
            for b in blockers:
                print(f"  - {b}")
        else:
            print("All automated gates passed.")
    return 0 if verdict == "PASS" else (2 if verdict == "CONDITIONAL" else 1)


if __name__ == "__main__":
    raise SystemExit(main())
