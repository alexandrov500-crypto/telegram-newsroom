from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def _smoothing_factor() -> float:
    try:
        return float(os.getenv("RHYTHM_SMOOTHING_FACTOR", "0.15"))
    except ValueError:
        return 0.15


def _published_counts(db_path: Path | None = None) -> dict[str, int]:
    from bot.storage.db import default_db_path, init_database

    path = init_database(db_path or default_db_path())
    out = {"2h": 0, "3h": 0, "6h": 0}
    for key, hours in (("2h", 2), ("3h", 3), ("6h", 6)):
        try:
            with sqlite3.connect(path, timeout=5) as conn:
                row = conn.execute(
                    """
                    SELECT COUNT(*) FROM published_posts
                    WHERE published_at >= datetime('now', ?)
                    """,
                    (f"-{hours} hours",),
                ).fetchone()
            out[key] = int(row[0] or 0) if row else 0
        except sqlite3.OperationalError:
            pass
    return out


def _hourly_publish_variance(hours: int = 24, db_path: Path | None = None) -> float | None:
    from bot.editorial.flow_health.trends import _hourly_snapshots

    snaps = _hourly_snapshots(hours, db_path)
    pubs = [int(s.get("published") or 0) for s in snaps]
    if len(pubs) < 3:
        return None
    mean = sum(pubs) / len(pubs)
    if mean < 0.01:
        return 0.0
    var = sum((p - mean) ** 2 for p in pubs) / len(pubs)
    return round(var ** 0.5 / max(mean, 0.5), 3)


def compute_rhythm_modulation(*, db_path: Path | None = None) -> dict[str, Any]:
    """
    Lazy rhythm smoothing — dampen recovery after bursts, nudge after silence.
    Modulation is advisory; applied only within relaxation budget path.
    """
    factor = _smoothing_factor()
    counts = _published_counts(db_path)
    p2, p3, p6 = counts["2h"], counts["3h"], counts["6h"]

    try:
        from bot.editorial.flow_health.degradation import gates_for_current_mode

        gates = gates_for_current_mode()
    except Exception:
        gates = {"rhythm_dampen": True, "surge_boost": True}

    burst = p2 >= int(os.getenv("RHYTHM_BURST_2H", "3")) or (
        p6 >= int(os.getenv("RHYTHM_BURST_6H", "6")) and p2 >= 2
    )
    if not gates.get("rhythm_dampen", True):
        burst = False
    silent = p3 == 0 and p6 < 2

    try:
        from bot.editorial.flow_health.funnel import funnel_summary

        fetched = int((funnel_summary().get("counters") or {}).get("FETCHED", 0))
    except Exception:
        fetched = 0

    silent = silent and fetched >= int(os.getenv("RHYTHM_SILENCE_MIN_FETCHED", "10"))

    multiplier = 1.0
    band = "steady"
    if burst:
        multiplier = max(0.55, 1.0 - factor)
        band = "burst_dampen"
    elif silent:
        multiplier = min(1.25, 1.0 + factor * 0.5)
        band = "silence_nudge"

    cadence_var = _hourly_publish_variance(24, db_path)
    stability = 1.0
    if cadence_var is not None:
        stability = round(max(0.0, 1.0 - min(1.0, cadence_var)), 3)

    surge_active = False
    medium_cycle_active = False
    try:
        from bot.editorial.flow_health.surge_balance import detect_news_surge, surge_rhythm_multiplier

        surge = detect_news_surge(db_path=str(db_path) if db_path else None)
        surge_active = bool(surge.get("surge_active")) and gates.get("surge_boost", True)
        if surge_active:
            multiplier = surge_rhythm_multiplier(multiplier, surge)
            if band == "burst_dampen":
                band = "surge_responsive"
    except Exception:
        pass

    try:
        from bot.editorial.flow_health.responsiveness import (
            apply_responsiveness_to_rhythm,
            compute_medium_cycle_responsiveness,
        )

        resp = compute_medium_cycle_responsiveness(db_path=db_path)
        medium_cycle_active = bool(resp.get("medium_cycle_active")) and gates.get(
            "responsiveness_boost",
            True,
        )
        if medium_cycle_active:
            multiplier = apply_responsiveness_to_rhythm(multiplier, resp)
            if band in ("burst_dampen", "steady"):
                band = "medium_cycle_responsive"
    except Exception:
        pass

    return {
        "rhythm_multiplier": round(multiplier, 4),
        "surge_active": surge_active,
        "medium_cycle_active": medium_cycle_active,
        "rhythm_band": band,
        "publishes_2h": p2,
        "publishes_6h": p6,
        "burst_detected": burst,
        "silence_detected": silent,
        "cadence_variance": cadence_var,
        "rhythm_stability": stability,
        "smoothing_factor": factor,
    }
