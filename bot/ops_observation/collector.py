from __future__ import annotations

import json
import sqlite3
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

from bot.observability.loop_health import get_loop_health, snapshot as loop_health_snapshot
from bot.ops_observation.anomalies import detect_anomalies
from pathlib import Path

from bot.storage.db import default_db_path, init_database


def _http_json(url: str, timeout: float = 8.0) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def _fetch_runtime_http(base: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for path in (
        "/runtime_identity",
        "/runtime_loops",
        "/runtime_performance",
        "/live_status",
        "/channel_health",
        "/health",
    ):
        try:
            out[path] = _http_json(f"{base.rstrip('/')}{path}")
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            out[path] = {"status": "error", "error": str(exc)[:200]}
    return out


def _db_publish_stats(db_path: Path | str, *, hours: int = 24) -> dict[str, Any]:
    path = Path(db_path)
    init_database(path)
    since = datetime.now(timezone.utc).isoformat()
    stats: dict[str, Any] = {
        "window_hours": hours,
        "published_24h": 0,
        "held_24h": 0,
        "by_source": {},
        "ratings": {"good": 0, "bad": 0},
    }
    try:
        with sqlite3.connect(str(path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT trace_json, created_at FROM live_publish_trace
                WHERE created_at >= datetime('now', ?)
                ORDER BY created_at DESC
                """,
                (f"-{hours} hours",),
            ).fetchall()
            for row in rows:
                try:
                    trace = json.loads(row["trace_json"] or "{}")
                except json.JSONDecodeError:
                    continue
                src = str(trace.get("source") or "unknown")
                by = stats["by_source"].setdefault(
                    src,
                    {"published": 0, "held": 0, "pass": 0},
                )
                if trace.get("published"):
                    stats["published_24h"] += 1
                    by["published"] += 1
                else:
                    stats["held_24h"] += 1
                    by["held"] += 1
                if str(trace.get("guard_result", "")).lower() == "pass":
                    by["pass"] += 1

            rating_rows = conn.execute(
                """
                SELECT rating, COUNT(*) AS c FROM live_channel_post_ratings
                WHERE created_at >= datetime('now', ?)
                GROUP BY rating
                """,
                (f"-{hours} hours",),
            ).fetchall()
            for rr in rating_rows:
                stats["ratings"][str(rr["rating"])] = int(rr["c"])
    except sqlite3.OperationalError:
        pass
    stats["since_query"] = since
    return stats


def collect_observation_pulse(
    *,
    base_url: str = "http://127.0.0.1:8080",
    db_path: str | None = None,
) -> dict[str, Any]:
    """Single observation pulse for 48h operational monitoring."""
    now = datetime.now(timezone.utc)
    http = _fetch_runtime_http(base_url)
    lh = loop_health_snapshot()
    health_tracker = get_loop_health()

    live = http.get("/live_status") or {}
    perf = http.get("/runtime_performance") or {}
    loops = http.get("/runtime_loops") or {}
    ident = http.get("/runtime_identity") or {}

    lag_max = float(
        perf.get("event_loop_lag_max")
        or (perf.get("context") or {}).get("event_loop_lag_max")
        or live.get("runtime_performance", {}).get("event_loop_lag_max")
        or 0.0,
    )

    pulse: dict[str, Any] = {
        "timestamp": now.isoformat(),
        "date": now.date().isoformat(),
        "phase": "operational_observation_48h",
        "runtime_instance_id": ident.get("runtime_instance_id"),
        "runtime_profile": ident.get("runtime_profile"),
        "pid": ident.get("pid"),
        "watchdog_active": ident.get("watchdog_active"),
        "live_mode": live.get("live_mode") or (live.get("state") or {}).get("live_mode"),
        "frozen": live.get("frozen") or (live.get("state") or {}).get("frozen"),
        "paused": live.get("paused") or (live.get("state") or {}).get("paused"),
        "publishes_this_hour": live.get("publishes_this_hour")
        or (live.get("state") or {}).get("publishes_this_hour"),
        "channel_health": (http.get("/channel_health") or {}).get("trust_score"),
        "event_loop_lag_max": lag_max,
        "event_loop_lag_avg": perf.get("event_loop_lag_avg"),
        "stalled_loops": loops.get("stalled") or [],
        "watchdog_monitored": loops.get("watchdog_monitored"),
        "recovery_attempt_count": lh.get("recovery_attempt_count", 0),
        "recovery_suppressed_count": lh.get("recovery_suppressed_count", 0),
        "stalled_loop_count_total": lh.get("stalled_loop_count", 0),
        "rss_loop_duration_avg": lh.get("rss_loop_duration_avg"),
        "loop_health": lh,
        "publish_stats_24h": _db_publish_stats(db_path or default_db_path()),
        "http": http,
    }

    pulse["anomalies"] = detect_anomalies(pulse)
    try:
        from bot.ops_forensics.drift import detect_operational_drift

        pulse["drift_warnings"] = detect_operational_drift(pulse)
    except Exception:
        pulse["drift_warnings"] = []
    pulse["severity"] = (
        "critical"
        if any(a.get("level") == "critical" for a in pulse["anomalies"])
        else "warning"
        if pulse["anomalies"] or pulse.get("drift_warnings")
        else "ok"
    )
    return pulse
