"""Aggregate final stability report for public launch decision."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.observability.release_contract import FinalVerdict
from app.observability.validation_contract import evaluate_release_contract, metric
from app.observability.validation_environment import detect_validation_environment, observational_policy


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def build_final_stability_report(runtime_dir: str) -> dict[str, Any]:
    rd = Path(runtime_dir).expanduser().resolve()
    e2e = _read_json(rd / "e2e_validation_report.json")
    sim = _read_json(rd / "telegram_live_simulation_report.json")
    burn = _read_json(rd / "burnin_validation.json")
    from app.observability.telegram_production import production_validation_report
    from app.observability.runtime_protection import protection_payload
    from app.observability.execution_graph_report import build_execution_graph_report
    from utils.database_url import sqlite_path_from_url

    dbp = sqlite_path_from_url(os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/newsroom.db"))
    eg = build_execution_graph_report(
        db_path=Path(dbp) if dbp and Path(dbp).is_file() else None,
        runtime_dir=rd,
        log_path=Path(os.getenv("NEWSROOM_LOG", "logs/local-run.log")),
        window_ticks=200,
    )
    tg = production_validation_report()
    prot = protection_payload(str(rd))
    from app.ops.live_rollback import rollback_active, rollback_payload

    rb_active = False
    rb = {}
    try:
        rb_active = rollback_active(str(rd))
        rb = rollback_payload(str(rd))
    except Exception:
        rb_active = False
    required_checks: list[dict[str, str]] = []
    observational_checks: list[dict[str, str]] = []

    eg_verdict = str(eg.get("verdict") or "UNKNOWN")
    if eg_verdict == "PASS":
        required_checks.append(metric("execution_graph_verdict", "PASS"))
    elif eg_verdict in {"FAIL", "CONDITIONAL"}:
        required_checks.append(
            metric("execution_graph_verdict", "FAIL", reason=f"verdict={eg_verdict.lower()}")
        )
    else:
        required_checks.append(metric("execution_graph_verdict", "UNKNOWN", reason="verdict_missing"))

    if str(prot.get("current_state") or "") == "critical":
        required_checks.append(metric("no_critical_runtime_events", "FAIL", reason="runtime_state_critical"))
    elif str(prot.get("current_state") or ""):
        required_checks.append(metric("no_critical_runtime_events", "PASS"))
    else:
        required_checks.append(metric("no_critical_runtime_events", "UNKNOWN", reason="runtime_state_missing"))

    if rb_active:
        required_checks.append(metric("rollback_state_stable", "FAIL", reason="rollback_active"))
    else:
        required_checks.append(metric("rollback_state_stable", "PASS"))

    e2e_publish = ((e2e.get("details") or {}).get("publish") or {}) if isinstance(e2e, dict) else {}
    dup = e2e_publish.get("duplicate_publish_paths")
    publish_without_finalize = e2e_publish.get("publish_without_finalize_proxy")
    if dup is None:
        required_checks.append(metric("no_duplicate_publish_detected", "UNKNOWN", reason="duplicate_metric_missing"))
    elif int(dup) > 0:
        required_checks.append(metric("no_duplicate_publish_detected", "FAIL", reason=f"duplicate_paths={dup}"))
    else:
        required_checks.append(metric("no_duplicate_publish_detected", "PASS"))

    if publish_without_finalize is None:
        required_checks.append(
            metric("publish_finalize_order_valid", "UNKNOWN", reason="publish_finalize_metric_missing")
        )
    elif int(publish_without_finalize) > 0:
        required_checks.append(
            metric(
                "publish_finalize_order_valid",
                "FAIL",
                reason=f"publish_without_finalize={publish_without_finalize}",
            )
        )
    else:
        required_checks.append(metric("publish_finalize_order_valid", "PASS"))

    if tg:
        if bool(tg.get("ok")):
            observational_checks.append(metric("telegram_health", "PASS", kind="observational"))
        else:
            observational_checks.append(
                metric("telegram_health", "FAIL", reason="telegram_health_degraded", kind="observational")
            )
    else:
        observational_checks.append(
            metric("telegram_health", "UNKNOWN", reason="telegram_health_missing", kind="observational")
        )

    cont = ((burn.get("metrics") or {}).get("publish_continuity") or {}).get("autonomous_continuity_score")
    if cont is None:
        observational_checks.append(
            metric("publish_continuity_score", "UNKNOWN", reason="continuity_missing", kind="observational")
        )
    elif float(cont) < float(os.getenv("PUBLIC_GO_MIN_CONTINUITY_SCORE", "55")):
        observational_checks.append(
            metric(
                "publish_continuity_score",
                "FAIL",
                reason=f"score_below_threshold:{cont}",
                kind="observational",
            )
        )
    else:
        observational_checks.append(metric("publish_continuity_score", "PASS", kind="observational"))

    # Keep fixed observational schema fields; UNKNOWN means signal missing.
    observational_checks.append(
        metric("traffic_metrics", "UNKNOWN", reason="traffic_metrics_not_available", kind="observational")
    )
    observational_checks.append(
        metric("latency_metrics", "UNKNOWN", reason="latency_metrics_not_available", kind="observational")
    )
    observational_checks.append(
        metric("engagement_proxy", "UNKNOWN", reason="engagement_proxy_not_available", kind="observational")
    )

    env_mode = detect_validation_environment()
    policy = observational_policy(env_mode)
    contract = evaluate_release_contract(
        source="final_stability_report",
        required=required_checks,
        observational=observational_checks,
        ignore_missing_observational=bool(policy.get("ignore_missing_observational")),
    )

    warnings = list(contract.get("warnings") or [])
    if str(prot.get("current_state")) == "elevated":
        warnings.append("runtime_elevated")

    blockers = list(contract.get("blockers") or [])
    verdict = str(contract.get("verdict") or FinalVerdict.NOT_READY.value)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "FINAL_STABILITY_VERDICT": verdict,
        "blockers": blockers,
        "warnings": warnings,
        "validation_environment": env_mode,
        "required_checks": required_checks,
        "observational_checks": observational_checks,
        "execution_graph_consistency": eg.get("consistency_rate"),
        "runtime_protection_events": prot,
        "publish_continuity_score": cont,
        "live_rollback": rb,
        "telegram_reliability_score": 100 if tg.get("ok") else 60,
        "openai_reliability_score": 100 if str(prot.get("current_state")) == "normal" else 70,
        "e2e_validation": e2e,
        "telegram_simulation": sim,
    }


def write_final_stability_report(runtime_dir: str, report: dict[str, Any]) -> Path:
    out = Path(runtime_dir).expanduser().resolve() / "final_stability_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out


async def run_final_stability_report_heartbeat(settings: Any) -> dict[str, Any]:
    rep = build_final_stability_report(settings.runtime_state_dir)
    write_final_stability_report(settings.runtime_state_dir, rep)
    return rep
