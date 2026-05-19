from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from bot.ops_observation.store import OpsObservationStore


def _week_pulse_summary(store: OpsObservationStore, *, days: int = 7) -> dict[str, Any]:
    now = datetime.now(timezone.utc).date()
    severities: Counter[str] = Counter()
    lag_max = 0.0
    pulse_count = 0
    anomaly_count = 0
    stalled_total = 0
    recovery_total = 0

    for i in range(days):
        day = (now - timedelta(days=i)).isoformat()
        path = store.pulses_dir / f"{day}.jsonl"
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                p = json.loads(line)
            except json.JSONDecodeError:
                continue
            pulse_count += 1
            severities[str(p.get("severity", "ok"))] += 1
            lag_max = max(lag_max, float(p.get("event_loop_lag_max") or 0))
            anomaly_count += len(p.get("anomalies") or [])
            stalled_total += len(p.get("stalled_loops") or [])
            recovery_total += int(p.get("recovery_attempt_count") or 0)

    return {
        "pulse_count": pulse_count,
        "severity_counts": dict(severities),
        "event_loop_lag_max": round(lag_max, 4),
        "anomaly_signals": anomaly_count,
        "stalled_loop_events": stalled_total,
        "recovery_attempts": recovery_total,
    }


def _week_daily_snapshots(store: OpsObservationStore, *, days: int = 7) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc).date()
    out: list[dict[str, Any]] = []
    for i in range(days):
        day = (now - timedelta(days=i)).isoformat()
        path = store.daily_dir / f"{day}.json"
        if not path.is_file():
            continue
        try:
            out.append(json.loads(path.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    return out


def build_runtime_weekly_summary(*, store: OpsObservationStore | None = None) -> dict[str, Any]:
    store = store or OpsObservationStore()
    pulse = _week_pulse_summary(store)
    dailies = _week_daily_snapshots(store)

    publish_rates: list[float] = []
    publish_counts: list[int] = []
    for d in dailies:
        rate = d.get("publish_success_rate")
        if rate is not None:
            publish_rates.append(float(rate))
        cnt = d.get("publishes_count")
        if cnt is not None:
            publish_counts.append(int(cnt))

    avg_rate = sum(publish_rates) / len(publish_rates) if publish_rates else None
    total_publishes = sum(publish_counts)

    return {
        "pulse": pulse,
        "daily_snapshots_loaded": len(dailies),
        "publish_success_rate_avg": round(avg_rate, 3) if avg_rate is not None else None,
        "publishes_total_7d": total_publishes,
        "stability": {
            "lag_trend": "elevated" if pulse["event_loop_lag_max"] > 0.5 else "normal",
            "stalled_loops": pulse["stalled_loop_events"],
            "recovery_storms": pulse["recovery_attempts"] > 5,
        },
    }


def week_db_publish_stats(db_path: Path, *, hours: int = 168) -> dict[str, Any]:
    import sqlite3

    from bot.storage.db import init_database

    init_database(db_path)
    out: dict[str, Any] = {
        "traces_total": 0,
        "published": 0,
        "held": 0,
        "ratings": {"good": 0, "bad": 0},
        "source_breakdown": {},
    }
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        traces = conn.execute(
            f"""
            SELECT trace_json FROM live_publish_trace
            WHERE created_at >= datetime('now', '-{hours} hours')
            """,
        ).fetchall()
        out["traces_total"] = len(traces)
        for row in traces:
            try:
                t = json.loads(row["trace_json"] or "{}")
            except json.JSONDecodeError:
                continue
            src = str(t.get("source") or "unknown")
            box = out["source_breakdown"].setdefault(src, {"published": 0, "total": 0})
            box["total"] += 1
            if t.get("published"):
                out["published"] += 1
                box["published"] += 1
            elif t.get("held") or t.get("blocked"):
                out["held"] += 1

        for row in conn.execute(
            f"""
            SELECT rating, COUNT(*) AS c FROM live_channel_post_ratings
            WHERE created_at >= datetime('now', '-{hours} hours')
            GROUP BY rating
            """,
        ):
            out["ratings"][str(row["rating"])] = int(row["c"])

        try:
            inc = conn.execute(
                f"""
                SELECT title, severity, created_at FROM live_channel_incidents
                WHERE created_at >= datetime('now', '-{hours} hours')
                ORDER BY created_at DESC LIMIT 20
                """,
            ).fetchall()
            out["incidents"] = [
                {"title": r["title"], "severity": r["severity"], "at": r["created_at"]}
                for r in inc
            ]
        except sqlite3.OperationalError:
            out["incidents"] = []

    if out["traces_total"]:
        out["success_rate"] = round(out["published"] / out["traces_total"], 3)
    return out
