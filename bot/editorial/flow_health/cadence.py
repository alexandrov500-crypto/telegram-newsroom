from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _parse_window_targets() -> list[tuple[int, int, int, int]]:
    """
    Config CADENCE_TARGETS format: "0-6:2-4,6-12:3-6,12-18:3-6,18-24:2-4"
    Returns list of (start_hour, end_hour, min_posts, max_posts) — end exclusive except 24 wraps.
    """
    raw = os.getenv(
        "CADENCE_TARGETS",
        "0-6:2-4,6-12:3-6,12-18:3-6,18-24:2-4",
    )
    windows: list[tuple[int, int, int, int]] = []
    for part in raw.split(","):
        part = part.strip()
        if not part or ":" not in part:
            continue
        hrs, counts = part.split(":", 1)
        if "-" not in hrs or "-" not in counts:
            continue
        h0, h1 = hrs.split("-", 1)
        c0, c1 = counts.split("-", 1)
        try:
            windows.append((int(h0), int(h1), int(c0), int(c1)))
        except ValueError:
            continue
    if not windows:
        windows = [(0, 6, 2, 4), (6, 12, 3, 6), (12, 18, 3, 6), (18, 24, 2, 4)]
    return windows


def expected_posts_for_hour(hour: int | None = None) -> dict[str, Any]:
    hour = hour if hour is not None else datetime.now(timezone.utc).hour
    for start, end, lo, hi in _parse_window_targets():
        if start <= end:
            if start <= hour < end:
                mid = (lo + hi) / 2.0
                return {"window": f"{start:02d}-{end:02d}", "min": lo, "max": hi, "expected": mid}
        elif hour >= start or hour < end:
            mid = (lo + hi) / 2.0
            return {"window": f"{start:02d}-{end:02d}", "min": lo, "max": hi, "expected": mid}
    return {"window": "default", "min": 2, "max": 4, "expected": 3.0}


def _published_count_hours(hours: float, db_path: Path | None = None) -> int:
    from bot.storage.db import default_db_path, init_database

    path = init_database(db_path or default_db_path())
    try:
        with sqlite3.connect(path, timeout=5) as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) FROM published_posts
                WHERE published_at >= datetime('now', ?)
                """,
                (f"-{int(hours)} hours",),
            ).fetchone()
        return int(row[0] or 0) if row else 0
    except sqlite3.OperationalError:
        return 0


def compute_cadence_health(*, db_path: Path | None = None) -> dict[str, Any]:
    """
    cadence_health = actual / expected for current UTC window (advisory modulation only).
    """
    exp = expected_posts_for_hour()
    expected = float(exp["expected"])
    window_hours = 6.0
    for start, end, _, _ in _parse_window_targets():
        if str(exp["window"]).startswith(f"{start:02d}"):
            window_hours = float((end - start) if end > start else (24 - start + end))
            break

    actual_window = _published_count_hours(window_hours, db_path)
    actual_6h = _published_count_hours(6, db_path)
    actual_24h = _published_count_hours(24, db_path)

    health_window = round(min(1.5, actual_window / expected), 3) if expected else 0.0
    health_6h = round(actual_6h / max(1.0, expected * 2), 3)

    band = "healthy"
    if health_window < 0.45:
        band = "under_cadence"
    elif health_window > 1.25:
        band = "ahead"

    return {
        "utc_hour": datetime.now(timezone.utc).hour,
        "expected_window": exp,
        "actual_window": actual_window,
        "actual_6h": actual_6h,
        "actual_24h": actual_24h,
        "cadence_health": health_window,
        "cadence_health_6h": health_6h,
        "cadence_band": band,
        "pilot_realistic": health_window >= 0.5 or actual_6h >= int(exp.get("min", 2)),
    }
