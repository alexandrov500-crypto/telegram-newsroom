#!/usr/bin/env python3
"""Final controlled-public-launch checklist — BLOCKED / CONDITIONAL / APPROVED."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from utils.database_url import sqlite_path_from_url


def _runtime_dir() -> Path:
    return Path(os.getenv("RUNTIME_STATE_DIR", "var/runtime"))


def _db_path() -> Path | None:
    raw = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/newsroom.db").strip()
    p = sqlite_path_from_url(raw)
    return Path(p) if p else None


def _check_systemd_unit() -> tuple[bool, str]:
    unit_repo = REPO / "deploy" / "systemd" / "newsroom.service"
    if not unit_repo.is_file():
        return False, "missing_deploy_unit:deploy/systemd/newsroom.service"
    if shutil.which("systemctl"):
        try:
            proc = subprocess.run(
                ["systemctl", "is-active", "newsroom"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            state = (proc.stdout or "").strip() or (proc.stderr or "").strip()
            if proc.returncode == 0 and state == "active":
                return True, "systemd_active"
            if state in ("inactive", "failed", "activating"):
                return False, f"systemd_not_active:{state}"
            return True, f"systemd_unit_present_local_check:{state or 'unknown'}"
        except (OSError, subprocess.TimeoutExpired) as exc:
            return True, f"systemd_unit_present_systemctl_skipped:{exc!r:.80}"
    return True, "systemd_unit_present_no_systemctl"


def run_checklist(*, write_report: Path | None = None) -> dict[str, object]:
    fails: list[str] = []
    warns: list[str] = []
    checks: dict[str, object] = {}

    ok_sd, sd_msg = _check_systemd_unit()
    checks["systemd"] = {"ok": ok_sd, "detail": sd_msg}
    if not ok_sd:
        fails.append(sd_msg)

    rd = _runtime_dir()
    db = _db_path()
    log_path = Path(os.getenv("NEWSROOM_LOG", "logs/local-run.log"))

    if not db or not db.is_file():
        fails.append("database_missing")
    else:
        import sqlite3

        conn = sqlite3.connect(str(db), timeout=5.0)
        try:
            from app.observability.publish_continuity import compute_autonomous_continuity_score

            continuity = compute_autonomous_continuity_score(conn, runtime_dir=str(rd))
            checks["continuity"] = continuity
            score = float(continuity.get("autonomous_continuity_score") or 0)
            min_score = float(os.getenv("FINAL_RELEASE_MIN_CONTINUITY", "55"))
            if score < min_score:
                fails.append(f"continuity_low:{score}")
            pub = conn.execute(
                "SELECT COUNT(*) FROM published_posts WHERE published_at >= datetime('now', '-24 hours')"
            ).fetchone()
            running = conn.execute(
                "SELECT COUNT(*) FROM pipeline_ticks WHERE finished_at IS NULL"
            ).fetchone()
            checks["publishes_24h"] = int(pub[0] if pub else 0)
            checks["running_ticks"] = int(running[0] if running else 0)
            if checks["running_ticks"] > 0:
                fails.append(f"scheduler_stuck_ticks:{checks['running_ticks']}")
        finally:
            conn.close()

        try:
            from app.observability.execution_graph_report import build_execution_graph_report

            eg = build_execution_graph_report(db_path=db, runtime_dir=rd, log_path=log_path, window_ticks=100)
            checks["execution_graph"] = {
                "ready": eg.get("execution_graph_ready"),
                "consistency": eg.get("consistency_rate"),
                "critical_ticks": eg.get("critical_tick_count"),
            }
            if not eg.get("execution_graph_ready"):
                fails.append("execution_graph_not_ready")
            if int(eg.get("critical_tick_count") or 0) > 0:
                fails.append(f"execution_graph_critical:{eg['critical_tick_count']}")
            if float(eg.get("consistency_rate") or 0) < 1.0:
                fails.append(f"execution_consistency:{eg.get('consistency_rate')}")
        except Exception as exc:
            warns.append(f"execution_graph_check_error:{exc!r:.120}")

        try:
            from app.observability.public_readiness import evaluate_final_public_readiness

            readiness = evaluate_final_public_readiness(db_path=db, runtime_dir=rd, log_path=log_path)
            checks["final_public_readiness"] = readiness.get("FINAL_PUBLIC_READINESS")
            for b in readiness.get("blockers") or []:
                if str(b) not in fails:
                    fails.append(str(b))
        except Exception as exc:
            warns.append(f"public_readiness_error:{exc!r:.120}")

    try:
        from app.observability.runtime_protection import protection_payload

        prot = protection_payload(str(rd))
        checks["runtime_protection"] = prot
        if str(prot.get("current_state") or "").lower() == "critical":
            fails.append("runtime_protection_critical")
    except Exception as exc:
        warns.append(f"runtime_protection_error:{exc!r:.80}")

    try:
        from app.ops.public_incident_safety import incident_payload

        inc = incident_payload(str(rd))
        checks["public_incident"] = inc
        if inc.get("frozen"):
            fails.append("public_incident_frozen")
    except Exception as exc:
        warns.append(f"incident_check_error:{exc!r:.80}")

    try:
        from app.observability.burnin_validation import load_burnin_validation

        burn = load_burnin_validation(str(rd))
        checks["burnin_verdict"] = burn.get("BURNIN_VERDICT")
        if burn.get("BURNIN_VERDICT") == "FAIL":
            fails.append("burnin_verdict_fail")
        elif burn.get("BURNIN_VERDICT") == "CONDITIONAL":
            warns.append("burnin_verdict_conditional")
    except Exception as exc:
        warns.append(f"burnin_validation_error:{exc!r:.80}")

    try:
        from app.ops.controlled_rollout import controlled_rollout_enabled, current_rollout_stage, rollout_stage_config

        checks["rollout"] = {
            "enabled": controlled_rollout_enabled(),
            "stage": current_rollout_stage().value,
            "config": rollout_stage_config().to_dict(),
        }
        if controlled_rollout_enabled() and os.getenv("ROLLOUT_STAGE", "").strip() == "":
            warns.append("rollout_enabled_default_stage")
    except Exception as exc:
        warns.append(f"rollout_check_error:{exc!r:.80}")

    try:
        from app.observability.prepublic_qa import prepublic_qa_enabled

        checks["prepublic_qa"] = prepublic_qa_enabled()
        stage = os.getenv("ROLLOUT_STAGE", "")
        if prepublic_qa_enabled() and stage == "STAGE_3_FULL_AUTONOMOUS":
            warns.append("qa_mode_with_full_autonomous_stage")
    except Exception:
        checks["prepublic_qa"] = False

    tg_state = rd / "telegram_production_state.json"
    checks["telegram_state_present"] = tg_state.is_file()
    if tg_state.is_file():
        try:
            tg = json.loads(tg_state.read_text(encoding="utf-8"))
            checks["telegram_consecutive_failures"] = int(tg.get("consecutive_api_failures") or 0)
            if checks["telegram_consecutive_failures"] >= int(
                os.getenv("FINAL_RELEASE_MAX_TELEGRAM_FAILURES", "5")
            ):
                fails.append(f"telegram_api_failures:{checks['telegram_consecutive_failures']}")
        except (OSError, json.JSONDecodeError):
            warns.append("telegram_state_unreadable")

    alerts_path = rd / "ops" / "pending_notifications.jsonl"
    if alerts_path.is_file():
        recent = alerts_path.read_text(encoding="utf-8", errors="replace").strip().splitlines()[-30:]
        crit = sum(1 for ln in recent if "critical" in ln.lower())
        checks["recent_critical_alerts"] = crit
        if crit >= int(os.getenv("FINAL_RELEASE_MAX_CRITICAL_ALERTS", "3")):
            fails.append(f"recent_critical_alerts:{crit}")

    if fails:
        verdict = "BLOCKED"
    elif warns:
        verdict = "CONDITIONAL"
    else:
        verdict = "APPROVED"

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "FINAL_RELEASE_VERDICT": verdict,
        "blockers": fails,
        "warnings": warns,
        "checks": checks,
    }

    if write_report:
        write_report.parent.mkdir(parents=True, exist_ok=True)
        write_report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    return report


def main() -> int:
    p = argparse.ArgumentParser(description="Final release checklist")
    p.add_argument("--json", action="store_true")
    p.add_argument(
        "--write",
        type=Path,
        default=Path(os.getenv("RUNTIME_STATE_DIR", "var/runtime")) / "FINAL_RELEASE_REPORT.json",
    )
    args = p.parse_args()
    report = run_checklist(write_report=args.write)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"FINAL_RELEASE_VERDICT: {report['FINAL_RELEASE_VERDICT']}")
        print(f"Report: {args.write}")
        if report["blockers"]:
            print("Blockers:")
            for b in report["blockers"]:
                print(f"  - {b}")
        if report["warnings"]:
            print("Warnings:")
            for w in report["warnings"]:
                print(f"  - {w}")
    v = str(report["FINAL_RELEASE_VERDICT"])
    return 0 if v == "APPROVED" else (2 if v == "CONDITIONAL" else 1)


if __name__ == "__main__":
    raise SystemExit(main())
