from __future__ import annotations

import json
import os
import sqlite3
import threading
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

_STAGES = (
    "FETCHED",
    "PARSED",
    "DEDUPED",
    "CLUSTERED",
    "SUMMARIZED",
    "QUALITY_PASSED",
    "QUARANTINED",
    "APPROVED",
    "PUBLISHED",
)

_lock = threading.Lock()
_counters: Counter[str] = Counter()
_rejections: Counter[str] = Counter()


def _enabled() -> bool:
    raw = os.getenv("PUBLISH_FLOW_HEALTH_ENABLED", "true").strip().lower()
    return raw in ("1", "true", "yes", "on")


def record_funnel(stage: str, *, rejection_reason: str | None = None) -> None:
    if not _enabled():
        return
    key = stage.upper()
    with _lock:
        if key in _STAGES:
            _counters[key] += 1
        if rejection_reason:
            _rejections[rejection_reason[:80]] += 1
    _maybe_flush()


def _hour_key(dt: datetime | None = None) -> str:
    dt = dt or datetime.now(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H")


def _maybe_flush() -> None:
    try:
        from bot.storage.db import default_db_path, init_database

        path = init_database(default_db_path())
        key = _hour_key()
        with _lock:
            payload = {
                "counters": dict(_counters),
                "rejections": dict(_rejections),
            }
        with sqlite3.connect(path, timeout=5) as conn:
            conn.execute(
                """
                INSERT INTO ops_publish_funnel_hourly (hour_key, counters_json, rejection_reasons_json, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(hour_key) DO UPDATE SET
                    counters_json = excluded.counters_json,
                    rejection_reasons_json = excluded.rejection_reasons_json,
                    updated_at = excluded.updated_at
                """,
                (
                    key,
                    json.dumps(payload["counters"]),
                    json.dumps(payload["rejections"]),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            conn.commit()
    except Exception:
        pass


def _load_window(hours: int, db_path: Path | None = None) -> tuple[Counter[str], Counter[str]]:
    totals: Counter[str] = Counter()
    rejects: Counter[str] = Counter()
    try:
        from bot.storage.db import default_db_path, init_database

        path = init_database(db_path or default_db_path())
        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%dT%H")
        with sqlite3.connect(path, timeout=5) as conn:
            rows = conn.execute(
                """
                SELECT counters_json, rejection_reasons_json FROM ops_publish_funnel_hourly
                WHERE hour_key >= ?
                """,
                (since,),
            ).fetchall()
        for row in rows:
            try:
                for k, v in json.loads(row[0] or "{}").items():
                    totals[k] += int(v)
            except (json.JSONDecodeError, TypeError):
                pass
            try:
                for k, v in json.loads(row[1] or "{}").items():
                    rejects[k] += int(v)
            except (json.JSONDecodeError, TypeError):
                pass
    except Exception:
        pass
    with _lock:
        totals.update(_counters)
        rejects.update(_rejections)
    return totals, rejects


def funnel_summary(*, hours: int | None = None, db_path: Path | None = None) -> dict[str, Any]:
    if hours is None:
        try:
            hours = int(os.getenv("STARVATION_WINDOW_HOURS", "6"))
        except ValueError:
            hours = 6

    totals, rejects = _load_window(hours, db_path)
    fetched = totals.get("FETCHED", 0)
    published = totals.get("PUBLISHED", 0)
    enqueued = totals.get("QUALITY_PASSED", 0) + totals.get("SUMMARIZED", 0)

    publish_ratio = round(published / fetched, 3) if fetched else None
    rejection_ratio = round(1.0 - (published / max(1, fetched)), 3) if fetched else None

    dominant_rejection = None
    if rejects:
        dominant_rejection = rejects.most_common(1)[0][0]

    starvation = detect_starvation(totals, hours=hours, rejects=rejects)

    return {
        "window_hours": hours,
        "counters": dict(totals),
        "publish_ratio": publish_ratio,
        "rejection_ratio": rejection_ratio,
        "dominant_rejection": dominant_rejection,
        "rejection_breakdown": dict(rejects.most_common(8)),
        "starvation": starvation,
        "enqueued_estimate": enqueued,
    }


def detect_starvation(
    totals: Counter[str] | dict[str, int],
    *,
    hours: int = 6,
    rejects: Counter[str] | None = None,
) -> dict[str, Any]:
    try:
        min_publish = int(os.getenv("MIN_PUBLISH_PER_6H", "3"))
    except ValueError:
        min_publish = 3
    try:
        min_fetched = int(os.getenv("STARVATION_MIN_FETCHED", "15"))
    except ValueError:
        min_fetched = 15

    if not os.getenv("PUBLISH_FLOOR_ENABLED", "true").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    ):
        return {"detected": False, "reason": "floor_disabled"}

    if isinstance(totals, Counter):
        t = totals
    else:
        t = Counter(totals)

    fetched = int(t.get("FETCHED", 0))
    published = int(t.get("PUBLISHED", 0))
    clustered = int(t.get("CLUSTERED", 0))

    coverage: dict[str, Any] = {}
    try:
        from bot.editorial.flow_health.coverage import compute_coverage_score

        coverage = compute_coverage_score(hours=hours)
    except Exception:
        coverage = {}

    volume_starved = fetched >= min_fetched and published < min_publish
    coverage_starved = fetched >= min_fetched and not coverage.get("coverage_sufficient", True)
    detected = volume_starved or coverage_starved

    rej = rejects if rejects is not None else Counter()
    attribution: dict[str, Any] = {}
    try:
        from bot.editorial.flow_health.attribution import attribute_starvation_causes

        attribution = attribute_starvation_causes(t, rej)
    except Exception:
        pass

    reason = None
    if detected:
        if coverage_starved and not volume_starved:
            reason = "insufficient_coverage"
        elif clustered >= fetched * 0.4:
            reason = "cluster_absorption"
        elif t.get("QUARANTINED", 0) > published * 2:
            reason = "guard_quarantine"
        elif t.get("DEDUPED", 0) > fetched * 0.5:
            reason = "dedupe_strict"
        else:
            reason = "low_publish_throughput"

    return {
        "detected": detected,
        "reason": reason,
        "fetched": fetched,
        "published": published,
        "min_publish": min_publish,
        "min_fetched": min_fetched,
        "hours": hours,
        "coverage": coverage,
        "attribution": attribution,
        "volume_starved": volume_starved,
        "coverage_starved": coverage_starved,
    }
