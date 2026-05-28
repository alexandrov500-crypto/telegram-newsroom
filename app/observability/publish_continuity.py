"""Autonomous publish continuity scoring and operator alerts."""

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


def _hours_since_publish(conn: sqlite3.Connection) -> float | None:
    row = conn.execute(
        """
        SELECT published_at FROM published_posts
        ORDER BY id DESC LIMIT 1
        """
    ).fetchone()
    if not row or not row[0]:
        return None
    try:
        dt = datetime.fromisoformat(str(row[0]).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).total_seconds() / 3600.0
    except (ValueError, TypeError):
        return None


def _tick_completion_rate(conn: sqlite3.Connection, *, hours: int = 24) -> float:
    row = conn.execute(
        """
        SELECT
          SUM(CASE WHEN finished_at IS NOT NULL THEN 1 ELSE 0 END),
          COUNT(*)
        FROM pipeline_ticks
        WHERE started_at >= datetime('now', ?)
        """,
        (f"-{hours} hours",),
    ).fetchone()
    finished, total = (row or (0, 0))
    if not total:
        return 1.0
    return round(int(finished or 0) / int(total), 4)


def _publish_success_rate(conn: sqlite3.Connection, *, hours: int = 24) -> float | None:
    try:
        pub = conn.execute(
            """
            SELECT COUNT(*) FROM published_posts
            WHERE published_at >= datetime('now', ?)
            """,
            (f"-{hours} hours",),
        ).fetchone()[0]
        drafts = conn.execute(
            """
            SELECT COUNT(*) FROM drafts
            WHERE created_at >= datetime('now', ?)
            """,
            (f"-{hours} hours",),
        ).fetchone()[0]
    except sqlite3.OperationalError:
        return None
    if int(drafts or 0) < 1:
        return None
    return round(min(1.0, int(pub or 0) / int(drafts)), 4)


def compute_autonomous_continuity_score(
    conn: sqlite3.Connection,
    *,
    runtime_dir: str | None = None,
) -> dict[str, Any]:
    from app.runtime_activity import activity_snapshot, seconds_since_scheduler_tick

    gap_h = _hours_since_publish(conn)
    tick_rate = _tick_completion_rate(conn)
    pub_rate = _publish_success_rate(conn)

    publish_continuity = 1.0
    max_gap = float(os.getenv("CONTINUITY_MAX_PUBLISH_GAP_HOURS", "12"))
    if gap_h is not None:
        if gap_h > max_gap:
            publish_continuity = 0.0
        else:
            publish_continuity = max(0.0, 1.0 - gap_h / max_gap)

    sched_sec = seconds_since_scheduler_tick()
    scheduler_ok = sched_sec is not None and sched_sec < float(
        os.getenv("CONTINUITY_SCHEDULER_STALE_SEC", "2700")
    )

    recovery_health = 1.0
    try:
        from app.observability.runtime_protection import load_protection_state, RuntimeHealthLevel

        st = load_protection_state(runtime_dir or os.getenv("RUNTIME_STATE_DIR", "var/runtime"))
        if str(st.get("current_state")) == RuntimeHealthLevel.CRITICAL.value:
            recovery_health = 0.3
        elif int(st.get("recovery_count") or 0) > int(os.getenv("CONTINUITY_MAX_RECOVERY_LOOPS", "3")):
            recovery_health = 0.5
    except Exception:
        pass

    latency_stability = 0.85
    try:
        from app.observability.runtime_health import load_health_snapshots

        snaps = load_health_snapshots(runtime_dir or "var/runtime", limit=10)
        pubs = [float(s.get("publish_latency_ms") or 0) for s in snaps if s.get("publish_latency_ms")]
        if len(pubs) >= 3:
            mean = sum(pubs) / len(pubs)
            var = sum((x - mean) ** 2 for x in pubs) / len(pubs)
            latency_stability = max(0.2, 1.0 - min(1.0, (var**0.5) / max(mean, 1.0)))
    except Exception:
        pass

    score = round(
        100.0
        * (
            0.35 * publish_continuity
            + 0.25 * tick_rate
            + 0.15 * (pub_rate or tick_rate)
            + 0.15 * recovery_health
            + 0.10 * latency_stability
        ),
        1,
    )
    if not scheduler_ok:
        score = min(score, 40.0)

    return {
        "autonomous_continuity_score": score,
        "publish_gap_hours": round(gap_h, 2) if gap_h is not None else None,
        "publish_continuity_component": round(publish_continuity, 3),
        "tick_completion_rate_24h": tick_rate,
        "publish_success_rate_24h": pub_rate,
        "scheduler_active": scheduler_ok,
        "seconds_since_scheduler_tick": sched_sec,
        "recovery_health_component": recovery_health,
        "publish_latency_stability": round(latency_stability, 3),
    }


def evaluate_continuity_alerts(
    conn: sqlite3.Connection,
    settings: Any,
) -> list[dict[str, Any]]:
    """Return alert payloads (caller enqueues to Telegram)."""
    alerts: list[dict[str, Any]] = []
    metrics = compute_autonomous_continuity_score(conn, runtime_dir=settings.runtime_state_dir)
    rd = settings.runtime_state_dir

    gap = metrics.get("publish_gap_hours")
    try:
        from app.ops.controlled_rollout import controlled_rollout_enabled, effective_alert_thresholds

        thresholds = effective_alert_thresholds() if controlled_rollout_enabled() else {}
        gap_thresh = float(thresholds.get("publish_gap_hours") or os.getenv("ALERT_PUBLISH_GAP_HOURS", "8"))
        continuity_min = float(
            thresholds.get("continuity_score_min") or os.getenv("ALERT_CONTINUITY_SCORE_MIN", "45")
        )
    except Exception:
        gap_thresh = float(os.getenv("ALERT_PUBLISH_GAP_HOURS", "8"))
        continuity_min = float(os.getenv("ALERT_CONTINUITY_SCORE_MIN", "45"))
    if gap is not None and gap > gap_thresh:
        alerts.append(
            _alert(
                kind="publish_gap",
                severity="critical",
                message=f"No channel publish for {gap:.1f}h (threshold {gap_thresh}h)",
                metrics=metrics,
                settings=settings,
            )
        )

    if not metrics.get("scheduler_active"):
        alerts.append(
            _alert(
                kind="scheduler_inactive",
                severity="critical",
                message="Scheduler tick stale or missing",
                metrics=metrics,
                settings=settings,
            )
        )

    try:
        from app.observability.runtime_protection import current_protection_level, RuntimeHealthLevel

        if current_protection_level(rd) == RuntimeHealthLevel.CRITICAL:
            alerts.append(
                _alert(
                    kind="runtime_critical",
                    severity="critical",
                    message="Runtime protection CRITICAL — autonomous publish frozen",
                    metrics=metrics,
                    settings=settings,
                )
            )
    except Exception:
        pass

    try:
        from app.ops.public_incident_safety import incident_frozen

        if incident_frozen(settings.runtime_state_dir):
            alerts.append(
                _alert(
                    kind="public_incident_frozen",
                    severity="critical",
                    message="Public incident safety freeze active — autonomous publish halted",
                    metrics=metrics,
                    settings=settings,
                )
            )
    except Exception:
        pass

    if float(metrics.get("autonomous_continuity_score") or 0) < continuity_min:
        alerts.append(
            _alert(
                kind="low_continuity_score",
                severity="warning",
                message=f"Autonomous continuity score low: {metrics.get('autonomous_continuity_score')}",
                metrics=metrics,
                settings=settings,
            )
        )

    return alerts


def _alert(
    *,
    kind: str,
    severity: str,
    message: str,
    metrics: dict[str, Any],
    settings: Any,
) -> dict[str, Any]:
    from app.observability.runtime_protection import protection_payload
    from app.runtime_activity import activity_snapshot

    act = activity_snapshot()
    return {
        "kind": kind,
        "severity": severity,
        "message": message,
        "probable_root_cause": _root_cause_hint(kind, metrics),
        "protection_state": protection_payload(settings.runtime_state_dir),
        "last_successful_publish_at": act.get("last_successful_publish_at"),
        "suggested_actions": _suggested_actions(kind),
        "metrics": metrics,
    }


def _root_cause_hint(kind: str, metrics: dict[str, Any]) -> str:
    if kind == "publish_gap":
        if not metrics.get("scheduler_active"):
            return "scheduler_stale"
        return "publish_path_blocked_or_no_drafts"
    if kind == "runtime_critical":
        return "runtime_degradation_protection"
    if kind == "scheduler_inactive":
        return "scheduler_or_process_issue"
    return "investigate_logs"


def _suggested_actions(kind: str) -> list[str]:
    if kind == "publish_gap":
        return [
            "make ops-status",
            "make autopublish-status",
            "check GLOBAL_PUBLISH_PAUSE and runtime_protection_state.json",
            "review /queue and pending drafts",
        ]
    if kind == "runtime_critical":
        return ["make stability-report", "resolve degradation flags", "/resume_autopublish when safe"]
    return ["make incident-report", "tail publish logs"]


async def run_continuity_checks_and_alert(settings: Any) -> dict[str, Any]:
    from utils.database_url import sqlite_path_from_url

    raw = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/newsroom.db").strip()
    path = sqlite_path_from_url(raw)
    if not path or not Path(path).is_file():
        return {"alerts": [], "metrics": {}}
    conn = sqlite3.connect(path, timeout=5.0)
    metrics = compute_autonomous_continuity_score(conn, runtime_dir=settings.runtime_state_dir)
    alerts = evaluate_continuity_alerts(conn, settings)
    conn.close()

    for al in alerts:
        if al.get("severity") != "critical" and al.get("kind") not in ("publish_gap", "scheduler_inactive"):
            continue
        from ops.operator_notifications import enqueue_operator_notification

        body = (
            f"{al['message']}\n"
            f"Cause: {al.get('probable_root_cause')}\n"
            f"Protection: {al.get('protection_state', {}).get('current_state')}\n"
            f"Last publish: {al.get('last_successful_publish_at')}\n"
            f"Actions: {', '.join(al.get('suggested_actions') or [])}"
        )
        enqueue_operator_notification(
            settings.runtime_state_dir,
            kind=str(al["kind"]),
            severity=str(al["severity"]),
            message=body[:400],
            fields=al,
        )
        log_event(logger, "publish_continuity.alert", kind=al["kind"], severity=al["severity"])

    try:
        from app.observability.telegram_production import run_telegram_production_checks_and_alert

        tg_out = await run_telegram_production_checks_and_alert(settings)
        return {"metrics": metrics, "alerts": alerts, "telegram_production": tg_out}
    except Exception as exc:
        log_event(logger, "telegram_production.heartbeat_failed", error=repr(exc)[:200])
        return {"metrics": metrics, "alerts": alerts}


def autopublish_pause_path(runtime_dir: str) -> Path:
    return Path(runtime_dir) / "operator_autopublish_pause.json"


def is_operator_autopublish_paused(runtime_dir: str) -> bool:
    path = autopublish_pause_path(runtime_dir)
    if not path.is_file():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return bool(data.get("paused"))
    except (OSError, json.JSONDecodeError):
        return False


def set_operator_autopublish_pause(runtime_dir: str, *, paused: bool, operator_id: int = 0) -> None:
    path = autopublish_pause_path(runtime_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "paused": paused,
                "operator_id": operator_id,
                "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
