"""Extended /health snapshot for pre-launch staging (sync SQLite reads)."""

from __future__ import annotations

import json
import os
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from utils.database_url import sqlite_path_from_url


def _db_path() -> str | None:
    raw = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/newsroom.db").strip()
    p = sqlite_path_from_url(raw)
    return str(p) if p else None


def _connect() -> sqlite3.Connection | None:
    path = _db_path()
    if not path:
        return None
    try:
        return sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2.0)
    except Exception:
        try:
            return sqlite3.connect(path, timeout=2.0)
        except Exception:
            return None


def _recent_ticks(conn: sqlite3.Connection, limit: int = 5) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT status, started_at, finished_at, posts_collected, drafts_created, failures,
               duration_ms, detail_json
        FROM pipeline_ticks
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        detail: dict[str, Any] = {}
        try:
            detail = json.loads(r[7] or "{}")
        except Exception:
            pass
        tick_duration = r[6]
        if tick_duration is None and r[1] and r[2]:
            try:
                s = datetime.fromisoformat(str(r[1]).replace("Z", "+00:00"))
                f = datetime.fromisoformat(str(r[2]).replace("Z", "+00:00"))
                tick_duration = int((f - s).total_seconds() * 1000)
            except Exception:
                pass
        out.append(
            {
                "status": r[0],
                "started_at": r[1],
                "finished_at": r[2],
                "posts_collected": int(r[3] or 0),
                "drafts_created": int(r[4] or 0),
                "failures": int(r[5] or 0) if isinstance(r[5], int) else 0,
                "duration_ms": tick_duration,
                "publish_outcome": detail.get("publish_outcome"),
            }
        )
    return out


def staging_health_snapshot() -> dict[str, Any]:
    from app.editorial.desk_starvation import desk_health_snapshot, desk_threshold_context
    from app.editorial.desk_thresholds import category_thresholds_snapshot
    from app.reliability.pipeline_health_hint import pipeline_health_hint

    now = datetime.now(timezone.utc)
    since_1h = (now - timedelta(hours=1)).isoformat()

    pipeline = dict(pipeline_health_hint())
    editorial = dict(desk_health_snapshot())
    editorial["category_thresholds"] = category_thresholds_snapshot(desk_threshold_context())
    try:
        from app.editorial.stability.slo import stability_slo_snapshot

        editorial["stability_slo"] = stability_slo_snapshot()
    except Exception:
        pass
    try:
        from app.editorial.growth_dominance.kpi import egdl_kpi_snapshot

        editorial["growth_dominance"] = egdl_kpi_snapshot()
    except Exception:
        pass
    try:
        from app.editorial.audience_unification.kpi import auh_kpi_snapshot

        editorial["audience_unification"] = auh_kpi_snapshot()
    except Exception:
        pass
    try:
        from app.editorial.unified_operating_system.kpi import ueos_kpi_snapshot

        editorial["ueos"] = ueos_kpi_snapshot()
    except Exception:
        pass
    try:
        from app.editorial.channel_product.kpi import channel_product_kpi_snapshot

        editorial["channel_product"] = channel_product_kpi_snapshot()
    except Exception:
        pass
    try:
        from app.editorial.product_os.kpi import product_os_kpi_snapshot

        editorial["product_os"] = product_os_kpi_snapshot()
    except Exception:
        pass
    try:
        from app.editorial.osgcp.kpi import osgcp_kpi_snapshot

        editorial["osgcp"] = osgcp_kpi_snapshot()
    except Exception:
        pass
    try:
        from app.editorial.ccd.kpi import ccd_kpi_snapshot

        editorial["ccd"] = ccd_kpi_snapshot()
    except Exception:
        pass
    try:
        from app.editorial.mpaes.kpi import mpaes_kpi_snapshot

        editorial["mpaes"] = mpaes_kpi_snapshot()
    except Exception:
        pass
    try:
        from app.editorial.ugsol.kpi import ugsol_kpi_snapshot

        editorial["ugsol"] = ugsol_kpi_snapshot()
    except Exception:
        pass
    try:
        from app.editorial.gmcs.kpi import gmcs_kpi_snapshot

        editorial["gmcs"] = gmcs_kpi_snapshot()
    except Exception:
        pass
    try:
        from app.editorial.eml.kpi import eml_kpi_snapshot

        editorial["eml"] = eml_kpi_snapshot()
    except Exception:
        pass
    try:
        from app.editorial.eaa.kpi import eaa_kpi_snapshot

        editorial["eaa"] = eaa_kpi_snapshot()
    except Exception:
        pass
    publishing: dict[str, Any] = {
        "published_1h": 0,
        "publish_failures_1h": 0,
        "drafts_pending": 0,
        "drafts_failed": 0,
        "retry_queue_pending": 0,
        "last_successful_publish": None,
        "last_publish_error": None,
        "telegram_errors_1h": 0,
    }
    runtime: dict[str, Any] = {
        "active_pid": os.getpid(),
        "active_process_id": os.getpid(),
        "uptime_sec": None,
        "singleton_lock_status": None,
        "singleton_lock_owner": None,
        "git_sha": None,
        "active_runtime": None,
        "restart_count": None,
    }
    bot_health: dict[str, Any] = {
        "handler_errors_total": 0,
        "handler_errors_1h": None,
        "event_loop_health": "unknown",
        "polling_active": None,
    }
    alerts: list[dict[str, Any]] = []

    conn = _connect()
    if conn:
        try:
            publishing["published_1h"] = int(
                conn.execute(
                    "SELECT COUNT(*) FROM published_posts WHERE published_at >= ?",
                    (since_1h,),
                ).fetchone()[0]
            )
            publishing["drafts_pending"] = int(
                conn.execute("SELECT COUNT(*) FROM drafts WHERE status = 'pending'").fetchone()[0]
            )
            publishing["drafts_failed"] = int(
                conn.execute("SELECT COUNT(*) FROM drafts WHERE status = 'failed'").fetchone()[0]
            )
            publishing["retry_queue_pending"] = int(
                conn.execute(
                    "SELECT COUNT(*) FROM failed_drafts WHERE status = 'pending'"
                ).fetchone()[0]
            )
            row = conn.execute(
                "SELECT published_at FROM published_posts ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if row and row[0]:
                publishing["last_successful_publish"] = row[0]
            publishing["publish_failures_1h"] = int(
                conn.execute(
                    "SELECT COUNT(*) FROM failed_drafts WHERE first_failed_at >= ?",
                    (since_1h,),
                ).fetchone()[0]
            )
            err_row = conn.execute(
                """
                SELECT id, status, last_publish_error FROM drafts
                WHERE status IN ('failed', 'publishing', 'pending')
                  AND last_publish_error IS NOT NULL AND last_publish_error != ''
                ORDER BY id DESC LIMIT 1
                """
            ).fetchone()
            if err_row:
                publishing["last_publish_error"] = {
                    "draft_id": int(err_row[0]),
                    "status": str(err_row[1]),
                    "error": str(err_row[2])[:500],
                }
            status_row = conn.execute(
                """
                SELECT id, status, moderated_at FROM drafts
                ORDER BY id DESC LIMIT 1
                """
            ).fetchone()
            if status_row:
                publishing["last_publish_status"] = {
                    "draft_id": int(status_row[0]),
                    "status": str(status_row[1]),
                    "at": status_row[2],
                }

            ticks = _recent_ticks(conn, limit=int(os.getenv("STAGING_TICK_LOOKBACK", "5")))
            pipeline["recent_ticks"] = ticks
            if ticks:
                last = ticks[0]
                pipeline["last_tick_at"] = last.get("finished_at") or last.get("started_at")
                pipeline["last_tick_duration_ms"] = last.get("duration_ms")
        finally:
            conn.close()

    try:
        from utils.metrics import export_snapshot

        c = export_snapshot().get("counters") or {}
        publishing["telegram_errors_1h"] = int(c.get("telegram_api_failures", 0))
        editorial["desk_included_total"] = int(c.get("desk_included_items_total", 0))
        editorial["desk_rejected_total"] = int(c.get("desk_rejected_items_total", 0))
        total = editorial["desk_included_total"] + editorial["desk_rejected_total"]
        editorial["approve_ratio"] = round(editorial["desk_included_total"] / total, 4) if total else None
        editorial["reject_ratio"] = round(editorial["desk_rejected_total"] / total, 4) if total else None
        pipeline["queue_depth"] = int((export_snapshot().get("gauges") or {}).get("queue_depth", 0))
    except Exception:
        pass

    editorial["top_reject_reasons"] = editorial.get("rejection_reason_breakdown") or {}

    starvation_active = bool(editorial.get("publish_starvation_detected"))
    pipeline["starvation_active"] = starvation_active

    try:
        from app.runtime_lifecycle import uptime_sec

        runtime["uptime_sec"] = round(uptime_sec(), 2)
    except Exception:
        pass
    try:
        from app.build_provenance import load_build_provenance

        prov = load_build_provenance()
        runtime["git_sha"] = prov.git_sha
        runtime["build_version"] = prov.build_version
    except Exception:
        pass
    try:
        from app.ops.runtime.active_runtime import load_active_runtime

        rd = os.getenv("RUNTIME_STATE_DIR", "var/runtime")
        runtime["active_runtime"] = load_active_runtime(rd)
    except Exception:
        pass
    try:
        from app.ops.runtime.singleton_guard import get_singleton_guard

        sg = get_singleton_guard(os.getenv("RUNTIME_STATE_DIR", "var/runtime"))
        owner = sg.is_owner()
        runtime["singleton_lock_owner"] = owner
        runtime["singleton_lock_status"] = "owner" if owner else "not_owner"
        runtime["singleton_lock_path"] = str(sg.path)
    except Exception:
        pass
    try:
        from app.dependency_state import get_dependency_state

        deps = get_dependency_state()
        bot_health["polling_active"] = deps.polling_active
        bot_health["event_loop_health"] = "ok" if deps.polling_active else "polling_inactive"
    except Exception:
        pass
    try:
        from utils.metrics import export_snapshot

        c = export_snapshot().get("counters") or {}
        bot_health["handler_errors_total"] = int(c.get("bot_handler_errors_total", 0))
        bot_health["handler_errors_1h"] = bot_health["handler_errors_total"]
    except Exception:
        pass
    pipeline["stuck_jobs_count"] = len(pipeline.get("stuck_jobs") or [])
    pipeline.setdefault("stuck_jobs", [])
    try:
        stuck_sec = float(os.getenv("PIPELINE_STUCK_TICK_SEC", "900"))
        conn2 = _connect()
        if conn2:
            rows = conn2.execute(
                """
                SELECT tick_id, started_at FROM pipeline_ticks
                WHERE status = 'running'
                ORDER BY started_at ASC LIMIT 10
                """
            ).fetchall()
            stuck: list[dict[str, Any]] = []
            for r in rows:
                started_raw = str(r[1] or "")
                try:
                    started = datetime.fromisoformat(started_raw.replace("Z", "+00:00"))
                    if started.tzinfo is None:
                        started = started.replace(tzinfo=timezone.utc)
                except ValueError:
                    continue
                age = (now - started).total_seconds()
                if age >= stuck_sec:
                    stuck.append({"tick_id": r[0], "started_at": r[1], "age_sec": round(age, 1)})
            pipeline["stuck_jobs"] = stuck
            conn2.close()
    except Exception:
        pipeline["stuck_jobs"] = []

    # --- Critical alerts ---
    n_ticks = int(os.getenv("STAGING_ZERO_DRAFT_TICKS", "3"))
    recent = pipeline.get("recent_ticks") or []
    if len(recent) >= n_ticks:
        window = recent[:n_ticks]
        if all(int(t.get("posts_collected") or 0) > 0 and int(t.get("drafts_created") or 0) == 0 for t in window):
            alerts.append(
                {
                    "severity": "critical",
                    "code": "pipeline.collect_without_drafts",
                    "message": f"collected>0 but drafts_created=0 for {n_ticks} ticks",
                }
            )

    fail_thresh = int(os.getenv("STAGING_PUBLISH_FAILURES_1H_WARN", "5"))
    if publishing["publish_failures_1h"] >= fail_thresh:
        alerts.append(
            {
                "severity": "high",
                "code": "publishing.degraded",
                "message": f"publish_failures_1h={publishing['publish_failures_1h']}",
            }
        )

    try:
        from app.openai_circuit import get_openai_circuit

        circ = get_openai_circuit().snapshot()
        if circ.get("openai_disabled") or str(circ.get("state")) == "open":
            alerts.append(
                {
                    "severity": "high",
                    "code": "openai.generation_degraded",
                    "message": f"circuit={circ.get('state')}",
                }
            )
    except Exception:
        pass

    if starvation_active and publishing["published_1h"] == 0:
        alerts.append(
            {
                "severity": "medium",
                "code": "editorial.starvation_recovery_active",
                "message": "no publishes in 1h while starvation recovery on",
            }
        )

    if pipeline.get("stuck_jobs"):
        alerts.append(
            {
                "severity": "high",
                "code": "pipeline.stuck_ticks",
                "message": f"stuck_running_ticks={len(pipeline['stuck_jobs'])}",
            }
        )

    transport_ok = True
    if publishing.get("last_publish_error"):
        err_txt = str((publishing["last_publish_error"] or {}).get("error") or "")
        if "disable_web_page_preview" in err_txt:
            recovered = int(publishing.get("published_1h") or 0) > 0
            if recovered:
                alerts.append(
                    {
                        "severity": "low",
                        "code": "publishing.historical_legacy_error_cleared",
                        "message": "post-recovery publish succeeded; retry remaining failed drafts",
                    }
                )
            else:
                transport_ok = False
                alerts.append(
                    {
                        "severity": "critical",
                        "code": "publishing.legacy_transport_kwargs",
                        "message": "last failure indicates stale runtime (disable_web_page_preview on media)",
                    }
                )

    if int(bot_health.get("handler_errors_total") or 0) > 20:
        alerts.append(
            {
                "severity": "medium",
                "code": "bot.handler_errors_elevated",
                "message": f"handler_errors_total={bot_health['handler_errors_total']}",
            }
        )

    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "pipeline": pipeline,
        "editorial": editorial,
        "publishing": publishing,
        "runtime": runtime,
        "bot": bot_health,
        "transport_layer_ok": transport_ok,
        "alerts": alerts,
        "launch_ready": len([a for a in alerts if a.get("severity") == "critical"]) == 0,
    }
