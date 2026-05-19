from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from bot.ops_lifecycle.db_health import database_health


def compute_entropy_metrics(
    db_path: Path,
    *,
    lifecycle_runs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Operational aging awareness — storage velocity, retention effectiveness."""
    health = database_health(db_path)
    tables = health.get("tables") or {}
    high_volume = sorted(
        ((k, v) for k, v in tables.items() if isinstance(v, int)),
        key=lambda kv: kv[1],
        reverse=True,
    )[:8]

    runs = lifecycle_runs or []
    last_removed = 0
    if runs:
        try:
            summary = runs[0].get("summary") or {}
            if isinstance(summary, str):
                summary = json.loads(summary)
            for r in summary.get("results") or []:
                last_removed += int(r.get("removed") or 0)
        except (json.JSONDecodeError, TypeError, KeyError):
            pass

    size_mb = float(health.get("size_mb") or 0)
    query_ms = health.get("query_samples_ms") or {}
    slow = any((v or 0) > 50 for v in query_ms.values() if v is not None)

    archive_pressure = "low"
    if size_mb > 500:
        archive_pressure = "high"
    elif size_mb > 150:
        archive_pressure = "medium"

    return {
        "db_size_mb": size_mb,
        "integrity_ok": health.get("integrity_ok"),
        "freelist_count": health.get("freelist_count"),
        "top_tables": high_volume,
        "query_degradation": slow,
        "archive_pressure": archive_pressure,
        "last_maintenance_rows_removed": last_removed,
        "retention_effectiveness": "active" if last_removed > 0 else "idle",
    }
