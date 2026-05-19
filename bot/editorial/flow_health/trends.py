from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def _hourly_snapshots(hours: int, db_path: Path | None = None) -> list[dict[str, Any]]:
    from bot.storage.db import default_db_path, init_database

    path = init_database(db_path or default_db_path())
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%dT%H")
    out: list[dict[str, Any]] = []
    try:
        with sqlite3.connect(path, timeout=5) as conn:
            rows = conn.execute(
                """
                SELECT hour_key, counters_json FROM ops_publish_funnel_hourly
                WHERE hour_key >= ? ORDER BY hour_key ASC
                """,
                (since,),
            ).fetchall()
        for row in rows:
            try:
                counters = json.loads(row[1] or "{}")
            except json.JSONDecodeError:
                counters = {}
            fetched = int(counters.get("FETCHED", 0))
            published = int(counters.get("PUBLISHED", 0))
            ratio = published / fetched if fetched else None
            out.append(
                {
                    "hour": row[0],
                    "publish_ratio": ratio,
                    "fetched": fetched,
                    "published": published,
                    "clustered": int(counters.get("CLUSTERED", 0)),
                },
            )
    except Exception:
        pass
    return out


def _trend_direction(values: list[float | None]) -> str:
    clean = [v for v in values if v is not None]
    if len(clean) < 2:
        return "insufficient_data"
    first_half = sum(clean[: len(clean) // 2]) / max(1, len(clean) // 2)
    second_half = sum(clean[len(clean) // 2 :]) / max(1, len(clean) - len(clean) // 2)
    if second_half > first_half * 1.15 + 0.02:
        return "rising"
    if second_half < first_half * 0.85 - 0.02:
        return "falling"
    return "stable"


def compute_flow_trends(*, db_path: Path | None = None) -> dict[str, Any]:
    from bot.editorial.flow_health.state import load_state

    windows = {}
    for hours, label in ((6, "6h"), (24, "24h"), (72, "72h")):
        snaps = _hourly_snapshots(hours, db_path)
        ratios = [s["publish_ratio"] for s in snaps]
        windows[label] = {
            "publish_ratio_trend": _trend_direction(ratios),
            "avg_publish_ratio": round(
                sum(r for r in ratios if r is not None) / max(1, len([r for r in ratios if r is not None])),
                3,
            )
            if any(r is not None for r in ratios)
            else None,
            "starvation_hours": sum(
                1
                for s in snaps
                if s.get("fetched", 0) >= 10 and (s.get("published") or 0) < 2
            ),
        }

    st = load_state()
    metrics = {k: v for k, v in st.items() if k != "recovery_activated_at"}
    relaxation_hist = metrics.get("relaxation_budget_history") or []
    if isinstance(relaxation_hist, list) and len(relaxation_hist) >= 2:
        relax_trend = _trend_direction([float(x) for x in relaxation_hist[-24:]])
    else:
        relax_trend = "insufficient_data"

    permissive_drift = (
        windows.get("24h", {}).get("publish_ratio_trend") == "rising"
        and relax_trend in ("rising", "stable")
        and windows.get("24h", {}).get("starvation_hours", 0) <= 1
    )

    cadence_by_window: dict[str, Any] = {}
    try:
        from bot.editorial.flow_health.cadence import compute_cadence_health

        cadence_by_window["current"] = compute_cadence_health(db_path=db_path)
    except Exception:
        cadence_by_window = {}

    return {
        "windows": windows,
        "cadence": cadence_by_window,
        "relaxation_trend": relax_trend,
        "permissive_drift_warning": permissive_drift,
        "drift_interpretation": (
            "System may be drifting permissive — review relaxation budget"
            if permissive_drift
            else "No strong permissive drift detected"
        ),
    }
