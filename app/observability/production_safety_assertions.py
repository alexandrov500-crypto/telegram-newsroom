"""Production runtime safety assertions (alerting + optional rollback activation)."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from utils.structured_log import log_event

import logging

logger = logging.getLogger(__name__)


def _assertion(
    name: str,
    ok: bool,
    *,
    detail: str = "",
    critical: bool = False,
) -> dict[str, Any]:
    return {"name": name, "ok": ok, "detail": detail[:240], "critical": critical}


def evaluate_production_safety_assertions(conn: sqlite3.Connection, *, runtime_dir: str) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []

    # no duplicate publish IDs
    dup = conn.execute(
        "SELECT COUNT(*) FROM (SELECT telegram_post_id, COUNT(*) c FROM published_posts GROUP BY telegram_post_id HAVING c>1)"
    ).fetchone()
    checks.append(_assertion("no_duplicate_publish_ids", int((dup or [0])[0] or 0) == 0, critical=True))

    # no publish without finalize (proxy: published draft must be in published status)
    unfinal = conn.execute(
        """
        SELECT COUNT(*) FROM published_posts pp
        JOIN drafts d ON d.id = pp.draft_id
        WHERE COALESCE(d.status, '') NOT IN ('published', 'approved', 'committed_draft')
        """
    ).fetchone()
    checks.append(_assertion("no_publish_without_finalize", int((unfinal or [0])[0] or 0) == 0, critical=True))

    # no finalize without summarize (proxy: finished tick with empty terminal reason marker)
    fin_wo_sum = conn.execute(
        """
        SELECT COUNT(*) FROM pipeline_ticks
        WHERE finished_at IS NOT NULL
          AND (detail_json IS NULL OR detail_json = '' OR detail_json = '{}')
          AND started_at >= datetime('now', '-24 hours')
        """
    ).fetchone()
    checks.append(_assertion("no_finalize_without_summarize", int((fin_wo_sum or [0])[0] or 0) == 0))

    # no publish without finalize / no finalize without summarize (state-machine approximation)
    running = conn.execute("SELECT COUNT(*) FROM pipeline_ticks WHERE finished_at IS NULL").fetchone()
    checks.append(_assertion("no_stale_tick_locks", int((running or [0])[0] or 0) <= int(os.getenv("ASSERT_MAX_STALE_TICKS", "0")), critical=True))

    # no runtime CRITICAL without alert
    try:
        from app.observability.runtime_protection import protection_payload

        state = protection_payload(runtime_dir)
        crit = str(state.get("current_state")) == "critical"
    except Exception:
        crit = False
    alerts_path = Path(runtime_dir).expanduser().resolve() / "ops" / "pending_notifications.jsonl"
    alert_hit = False
    if alerts_path.is_file():
        tail = alerts_path.read_text(encoding="utf-8", errors="replace").splitlines()[-100:]
        alert_hit = any("critical" in ln.lower() for ln in tail)
    checks.append(_assertion("no_runtime_critical_without_alert", (not crit) or alert_hit, critical=True))

    # no silent recovery loop
    try:
        from app.observability.runtime_protection import load_protection_state

        st = load_protection_state(runtime_dir)
        loops = int(st.get("recovery_count") or 0)
    except Exception:
        loops = 0
    checks.append(_assertion("no_silent_recovery_loop", loops <= int(os.getenv("ASSERT_MAX_RECOVERY_LOOPS", "6")), detail=f"recovery_count={loops}"))

    # no queue starvation > threshold / stale lock threshold
    try:
        from app.runtime_activity import seconds_since_scheduler_tick

        since = seconds_since_scheduler_tick()
        stale = since is not None and since > float(os.getenv("ASSERT_MAX_SCHEDULER_STALE_SEC", "3600"))
    except Exception:
        stale = False
    checks.append(_assertion("no_queue_starvation", not stale, critical=True))

    return checks


def _maybe_activate_rollback(runtime_dir: str, failed: list[dict[str, Any]]) -> None:
    if not failed:
        return
    if not (os.getenv("ASSERT_ACTIVATE_ROLLBACK_ON_FAIL", "true").strip().lower() in {"1", "true", "yes", "on"}):
        return
    try:
        from app.ops.live_rollback import activate_live_rollback

        activate_live_rollback(
            runtime_dir,
            reason="production_safety_assertion_failed:" + ",".join([f["name"] for f in failed][:4]),
            operator_id=0,
        )
    except Exception:
        pass


async def run_production_safety_assertions_heartbeat(settings: Any) -> dict[str, Any]:
    from utils.database_url import sqlite_path_from_url
    from ops.operator_notifications import enqueue_operator_notification

    raw = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/newsroom.db").strip()
    db_path = sqlite_path_from_url(raw)
    if not db_path or not Path(db_path).is_file():
        return {"skipped": True, "reason": "db_unavailable"}
    conn = sqlite3.connect(db_path, timeout=5.0)
    try:
        checks = evaluate_production_safety_assertions(conn, runtime_dir=settings.runtime_state_dir)
    finally:
        conn.close()
    failed = [c for c in checks if not c["ok"]]
    if failed:
        for c in failed:
            log_event(
                logger,
                "production_safety_assertion_failed",
                assertion=c["name"],
                detail=c["detail"],
                critical=c["critical"],
            )
        enqueue_operator_notification(
            settings.runtime_state_dir,
            kind="production_safety_assertion_failed",
            severity="critical" if any(c["critical"] for c in failed) else "warning",
            message=f"Safety assertion(s) failed: {', '.join(c['name'] for c in failed[:6])}",
            fields={"failed": failed},
        )
        _maybe_activate_rollback(settings.runtime_state_dir, failed)
    return {"checked": len(checks), "failed": failed}
