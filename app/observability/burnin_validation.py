"""Burn-in validation — rolling operational verdict (FAIL / CONDITIONAL / PASS)."""

from __future__ import annotations

import json
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from utils.structured_log import log_event

import logging

logger = logging.getLogger(__name__)

BURNIN_VERDICT_FAIL = "FAIL"
BURNIN_VERDICT_CONDITIONAL = "CONDITIONAL"
BURNIN_VERDICT_PASS = "PASS"


def _validation_path(runtime_dir: str) -> Path:
    return Path(runtime_dir).expanduser().resolve() / "burnin_validation.json"


def _uptime_sec() -> float:
    try:
        from app.observability.runtime_health import load_health_snapshots

        snaps = load_health_snapshots(os.getenv("RUNTIME_STATE_DIR", "var/runtime"), limit=1)
        if snaps and snaps[0].get("uptime_sec") is not None:
            return float(snaps[0]["uptime_sec"])
    except Exception:
        pass
    return round(time.monotonic(), 1)


def _operator_interventions(runtime_dir: str) -> dict[str, Any]:
    interventions: list[str] = []
    try:
        from app.observability.publish_continuity import is_operator_autopublish_paused

        if is_operator_autopublish_paused(runtime_dir):
            interventions.append("operator_autopublish_paused")
    except Exception:
        pass
    try:
        from app.ops.runtime_control import RuntimeControlMode, load_runtime_control

        if load_runtime_control(runtime_dir) == RuntimeControlMode.PAUSED:
            interventions.append("runtime_control_paused")
    except Exception:
        pass
    try:
        from app.ops.public_incident_safety import incident_frozen

        if incident_frozen(runtime_dir):
            interventions.append("public_incident_frozen")
    except Exception:
        pass
    return {"count": len(interventions), "active": interventions}


def _telegram_reliability() -> dict[str, Any]:
    from app.runtime_activity import activity_snapshot, seconds_since_collect

    act = activity_snapshot()
    since_collect = seconds_since_collect()
    collect_ok = since_collect is not None and since_collect < float(os.getenv("BURNIN_TELEGRAM_COLLECT_STALE_SEC", "7200"))
    return {
        "last_successful_collect_at": act.get("last_successful_collect_at"),
        "last_collect_failure_at": act.get("last_collect_failure_at"),
        "seconds_since_collect": since_collect,
        "collect_recent": collect_ok,
    }


def _openai_reliability() -> dict[str, Any]:
    from app.openai_circuit import get_openai_circuit

    circuit = get_openai_circuit()
    state = circuit.state().value
    from app.runtime_activity import activity_snapshot, seconds_since_ai

    act = activity_snapshot()
    since_ai = seconds_since_ai()
    return {
        "circuit_state": state,
        "circuit_allows_requests": circuit.allow_request(),
        "last_successful_ai_at": act.get("last_successful_ai_at"),
        "seconds_since_ai": since_ai,
        "healthy": state == "closed",
    }


def _runtime_drift(runtime_dir: str) -> dict[str, Any]:
    from app.observability.runtime_health import load_health_snapshots

    snaps = load_health_snapshots(runtime_dir, limit=12)
    drifts = [float(s.get("rss_drift_mb") or 0) for s in snaps if s.get("rss_drift_mb") is not None]
    flags = []
    for s in snaps[-5:]:
        flags.extend(list(s.get("degradation_flags") or []))
    return {
        "samples": len(snaps),
        "max_rss_drift_mb": round(max(drifts), 2) if drifts else None,
        "recent_degradation_flags": sorted(set(flags))[:16],
    }


def _recovery_metrics(runtime_dir: str) -> dict[str, Any]:
    from app.observability.runtime_protection import load_protection_state

    st = load_protection_state(runtime_dir)
    return {
        "current_state": st.get("current_state"),
        "recovery_count": int(st.get("recovery_count") or 0),
        "protection_activation_count": int(st.get("protection_activation_count") or 0),
        "last_critical_at": st.get("last_critical_at"),
    }


def _scheduler_stability() -> dict[str, Any]:
    from app.runtime_activity import seconds_since_scheduler_tick

    stale_sec = float(os.getenv("CONTINUITY_SCHEDULER_STALE_SEC", "2700"))
    since = seconds_since_scheduler_tick()
    active = since is not None and since < stale_sec
    return {
        "seconds_since_scheduler_tick": since,
        "scheduler_active": active,
        "stale_threshold_sec": stale_sec,
    }


def compute_burnin_verdict(metrics: dict[str, Any]) -> tuple[str, list[str]]:
    reasons: list[str] = []

    continuity = metrics.get("publish_continuity") or {}
    score = float(continuity.get("autonomous_continuity_score") or 0)
    if not continuity.get("scheduler_active"):
        reasons.append("scheduler_inactive")
    if score < float(os.getenv("BURNIN_FAIL_CONTINUITY_SCORE", "35")):
        reasons.append(f"continuity_score_low:{score}")

    recovery = metrics.get("recovery") or {}
    if str(recovery.get("current_state")) == "critical":
        reasons.append("runtime_protection_critical")

    telegram = metrics.get("telegram_reliability") or {}
    if not telegram.get("collect_recent") and telegram.get("seconds_since_collect") is not None:
        reasons.append("telegram_collect_stale")

    openai = metrics.get("openai_reliability") or {}
    if not openai.get("healthy"):
        reasons.append(f"openai_circuit:{openai.get('circuit_state')}")

    drift = metrics.get("runtime_drift") or {}
    max_drift = drift.get("max_rss_drift_mb")
    if max_drift is not None and float(max_drift) > float(os.getenv("BURNIN_FAIL_RSS_DRIFT_MB", "512")):
        reasons.append(f"runtime_drift_high:{max_drift}")

    if int((metrics.get("operator_interventions") or {}).get("count") or 0) >= 2:
        reasons.append("multiple_operator_interventions_active")

    fail_markers = ("runtime_protection_critical", "scheduler_inactive", "continuity_score_low")
    if any(any(m in r for m in fail_markers) for r in reasons):
        return BURNIN_VERDICT_FAIL, reasons

    conditional_markers = (
        "telegram_collect_stale",
        "openai_circuit",
        "runtime_drift_high",
        "operator_interventions",
    )
    if any(any(m in r for m in conditional_markers) for r in reasons):
        return BURNIN_VERDICT_CONDITIONAL, reasons
    if score < float(os.getenv("BURNIN_CONDITIONAL_CONTINUITY_SCORE", "55")):
        return BURNIN_VERDICT_CONDITIONAL, [f"continuity_score_moderate:{score}"]
    return BURNIN_VERDICT_PASS, []


def build_burnin_validation_report(
    conn: sqlite3.Connection,
    *,
    runtime_dir: str,
    log_path: Path | None = None,
) -> dict[str, Any]:
    from app.observability.burnin_eval import build_snapshot
    from app.observability.publish_continuity import compute_autonomous_continuity_score

    continuity = compute_autonomous_continuity_score(conn, runtime_dir=runtime_dir)
    recovery = _recovery_metrics(runtime_dir)
    metrics = {
        "uptime_sec": _uptime_sec(),
        "publish_continuity": continuity,
        "recovery": recovery,
        "telegram_reliability": _telegram_reliability(),
        "openai_reliability": _openai_reliability(),
        "runtime_drift": _runtime_drift(runtime_dir),
        "scheduler_stability": _scheduler_stability(),
        "operator_interventions": _operator_interventions(runtime_dir),
    }
    verdict, reasons = compute_burnin_verdict(metrics)
    tick_snap: dict[str, Any] = {}
    try:
        tick_snap = build_snapshot(conn, log_path=log_path)
    except Exception as exc:
        tick_snap = {"error": repr(exc)[:200]}
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "burnin_verdict": verdict,
        "verdict_reasons": reasons,
        "metrics": metrics,
        "tick_contract": {
            "verdict": tick_snap.get("verdict"),
            "readiness_reasons": tick_snap.get("readiness_reasons"),
            "tail_consecutive_finished_count": tick_snap.get("tail_consecutive_finished_count"),
        },
    }


def persist_burnin_validation(runtime_dir: str, report: dict[str, Any]) -> Path:
    path = _validation_path(runtime_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def load_burnin_validation(runtime_dir: str) -> dict[str, Any]:
    path = _validation_path(runtime_dir)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


async def run_burnin_validation_heartbeat(settings: Any) -> dict[str, Any]:
    """Scheduler heartbeat hook — persist burnin_validation.json."""
    from utils.database_url import sqlite_path_from_url

    runtime_dir = settings.runtime_state_dir
    raw = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/newsroom.db").strip()
    db_path = sqlite_path_from_url(raw)
    if not db_path or not Path(db_path).is_file():
        return {"skipped": True, "reason": "db_unavailable"}
    log_path = Path(os.getenv("NEWSROOM_LOG", "logs/local-run.log"))
    conn = sqlite3.connect(db_path, timeout=5.0)
    try:
        report = build_burnin_validation_report(conn, runtime_dir=runtime_dir, log_path=log_path)
    finally:
        conn.close()
    dest = persist_burnin_validation(runtime_dir, report)
    log_event(
        logger,
        "burnin_validation.heartbeat",
        verdict=report.get("burnin_verdict"),
        path=str(dest),
    )
    return report
