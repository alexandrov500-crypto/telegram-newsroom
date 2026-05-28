"""Component health probes for autonomous operations (read-only)."""

from __future__ import annotations

import os
import sqlite3
import time
from datetime import datetime, timezone
from typing import Any

from utils.database_url import sqlite_path_from_url


def _db_path() -> str | None:
    raw = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/newsroom.db").strip()
    path = sqlite_path_from_url(raw)
    return str(path) if path else None


def _query_one(sql: str, params: tuple = ()) -> Any:
    db = _db_path()
    if not db:
        return None
    try:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=2.0)
    except Exception:
        conn = sqlite3.connect(db, timeout=2.0)
    try:
        return conn.execute(sql, params).fetchone()
    except Exception:
        return None
    finally:
        conn.close()


def check_runtime_health() -> dict[str, Any]:
    from app.dependency_state import get_dependency_state

    deps = get_dependency_state()
    lease_age = None
    try:
        snap = deps.health_payload() if deps else {}
        exec_block = snap.get("execution") or {}
        lease = exec_block.get("lease") or {}
        lease_age = lease.get("age_sec")
    except Exception:
        snap = {}
    running_ticks = _query_one("SELECT COUNT(*) FROM pipeline_ticks WHERE finished_at IS NULL")
    stale_running = _query_one(
        """
        SELECT COUNT(*) FROM pipeline_ticks
        WHERE finished_at IS NULL
          AND started_at < datetime('now', '-3600 seconds')
        """
    )
    ok = (running_ticks or (0,))[0] <= 2 and (stale_running or (0,))[0] == 0
    return {
        "ok": ok,
        "startup_complete": bool(getattr(deps, "startup_complete", False)),
        "lease_age_sec": lease_age,
        "running_ticks": int((running_ticks or (0,))[0]),
        "stale_running_ticks": int((stale_running or (0,))[0]),
    }


def check_pipeline_health() -> dict[str, Any]:
    last = _query_one(
        """
        SELECT id, status, finished_at,
               json_extract(detail_json, '$.terminal_state') AS ts
        FROM pipeline_ticks
        WHERE finished_at IS NOT NULL
        ORDER BY id DESC LIMIT 1
        """
    )
    hour_ago = _query_one(
        """
        SELECT COUNT(*) FROM pipeline_ticks
        WHERE finished_at >= datetime('now', '-1 hour')
        """
    )
    rejects = _query_one(
        """
        SELECT COUNT(*) FROM pipeline_ticks
        WHERE finished_at >= datetime('now', '-24 hours')
          AND json_extract(detail_json, '$.terminal_state') = 'committed_reject'
        """
    )
    drafts = _query_one(
        """
        SELECT COUNT(*) FROM pipeline_ticks
        WHERE finished_at >= datetime('now', '-24 hours')
          AND json_extract(detail_json, '$.terminal_state') = 'committed_draft'
        """
    )
    progressing = bool(last and last[2])
    ok = progressing and int((hour_ago or (0,))[0]) >= 0
    return {
        "ok": ok,
        "last_tick_id": int(last[0]) if last else None,
        "last_status": last[1] if last else None,
        "last_terminal_state": last[3] if last else None,
        "ticks_last_hour": int((hour_ago or (0,))[0]),
        "committed_draft_24h": int((drafts or (0,))[0]),
        "committed_reject_24h": int((rejects or (0,))[0]),
    }


def check_telegram_health(settings: Any | None = None) -> dict[str, Any]:
    try:
        from app.dependency_state import get_dependency_state

        snap = get_dependency_state().health_payload()
        tg = snap.get("telegram_connectivity") or snap.get("checks", {}).get("telegram")
        ok = snap.get("status") != "unhealthy" and bool(
            snap.get("telegram_polling") or snap.get("telegram_connectivity_ok")
        )
        if isinstance(tg, dict):
            ok = ok and tg.get("ok", True) is not False
        return {"ok": ok, "detail": tg or snap.get("telegram_connectivity")}
    except Exception as exc:
        return {"ok": False, "error": repr(exc)[:200]}


def check_openai_health() -> dict[str, Any]:
    degraded = False
    fallback_active = os.getenv("BURNIN_OPENAI_ALWAYS_FALLBACK", "").lower() in ("1", "true", "yes")
    log_path = os.getenv("NEWSROOM_LOG", "logs/local-run.log")
    p = os.path.join(os.getcwd(), log_path) if log_path else ""
    if p and os.path.isfile(p):
        try:
            with open(p, "rb") as fh:
                fh.seek(0, 2)
                size = fh.tell()
                fh.seek(max(0, size - 500_000))
                chunk = fh.read().decode("utf-8", errors="replace")
            degraded = "openai.summarize_failed" in chunk or "429" in chunk
            fallback_active = fallback_active or "rule_fallback" in chunk
        except Exception:
            pass
    return {
        "ok": True,
        "degraded": degraded,
        "fallback_active": fallback_active,
        "quota_policy": "fallback_on_failure" if fallback_active else "primary_with_fallback_on_starvation",
    }


def gather_component_health(settings: Any | None = None) -> dict[str, Any]:
    runtime = check_runtime_health()
    pipeline = check_pipeline_health()
    telegram = check_telegram_health(settings)
    openai_h = check_openai_health()
    overall = all(
        [
            runtime.get("ok"),
            pipeline.get("ok"),
            telegram.get("ok"),
        ]
    )
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "ok": overall,
        "runtime": runtime,
        "pipeline": pipeline,
        "telegram": telegram,
        "openai": openai_h,
    }
