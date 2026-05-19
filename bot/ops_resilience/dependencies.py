from __future__ import annotations

from pathlib import Path
from typing import Any

from bot.ops_resilience.types import DEPENDENCIES, DependencyHealthBand


def classify_dependencies(
    *,
    pulse: dict[str, Any],
    db_path: Path | None = None,
) -> dict[str, dict[str, Any]]:
    """Health bands per dependency from observation pulse and runtime signals."""
    http = pulse.get("http") or {}
    channel = http.get("/channel_health") or {}
    health = http.get("/health") or {}
    lag = float(pulse.get("event_loop_lag_max") or 0)
    stalled = pulse.get("stalled_loops") or []
    recovery = int(pulse.get("recovery_attempt_count") or 0)

    from bot.runtime.state import runtime_state

    telegram_err = runtime_state.telegram_last_error
    telegram_ok = runtime_state.telegram_connected and not telegram_err

    bands: dict[str, dict[str, Any]] = {}

    if not telegram_ok or channel.get("status") == "error":
        tb = DependencyHealthBand.CRITICAL if telegram_err else DependencyHealthBand.UNSTABLE
    elif lag > 0.3 or "/live_status" in str(http.get("/live_status", {})):
        tb = DependencyHealthBand.DEGRADED
    else:
        tb = DependencyHealthBand.HEALTHY
    bands["telegram_api"] = {
        "band": tb.value,
        "connected": telegram_ok,
        "last_error": (telegram_err or "")[:120] or None,
    }

    rss_avg = float((pulse.get("loop_health") or {}).get("rss_loop_duration_avg") or 0)
    if rss_avg > 45 or lag > 0.5:
        rb = DependencyHealthBand.UNSTABLE
    elif rss_avg > 25:
        rb = DependencyHealthBand.DEGRADED
    else:
        rb = DependencyHealthBand.HEALTHY
    bands["rss_ingestion"] = {"band": rb.value, "rss_loop_duration_avg": rss_avg}

    sqlite_band = DependencyHealthBand.HEALTHY
    db_detail: dict[str, Any] = {}
    if db_path:
        try:
            from bot.ops_lifecycle.entropy import compute_entropy_metrics

            ent = compute_entropy_metrics(db_path)
            db_detail = ent
            size_mb = float(ent.get("db_size_mb") or 0)
            if not ent.get("integrity_ok", True):
                sqlite_band = DependencyHealthBand.CRITICAL
            elif size_mb > 500 or ent.get("archive_pressure") == "high":
                sqlite_band = DependencyHealthBand.DEGRADED
            elif size_mb > 200:
                sqlite_band = DependencyHealthBand.DEGRADED
        except Exception:
            sqlite_band = DependencyHealthBand.DEGRADED
    bands["sqlite"] = {"band": sqlite_band.value, **db_detail}

    openai_band = DependencyHealthBand.HEALTHY
    if health.get("status") not in (None, "ok", "healthy"):
        openai_band = DependencyHealthBand.DEGRADED
    bands["openai_api"] = {"band": openai_band.value, "health_status": health.get("status")}

    fs_band = DependencyHealthBand.HEALTHY
    try:
        from bot.config import project_root

        root = project_root()
        usage = _disk_usage_pct(root)
        if usage > 92:
            fs_band = DependencyHealthBand.CRITICAL
        elif usage > 85:
            fs_band = DependencyHealthBand.UNSTABLE
        elif usage > 75:
            fs_band = DependencyHealthBand.DEGRADED
        bands["filesystem"] = {"band": fs_band.value, "disk_used_pct": usage}
    except Exception:
        bands["filesystem"] = {"band": DependencyHealthBand.DEGRADED.value}

    if recovery > 5 or stalled:
        mb = DependencyHealthBand.UNSTABLE
    elif recovery > 2:
        mb = DependencyHealthBand.DEGRADED
    else:
        mb = DependencyHealthBand.HEALTHY
    bands["background_maintenance"] = {
        "band": mb.value,
        "recovery_attempts": recovery,
        "stalled_loops": len(stalled),
    }

    for dep in DEPENDENCIES:
        bands.setdefault(dep, {"band": DependencyHealthBand.HEALTHY.value})

    return bands


def _disk_usage_pct(path: Path) -> float:
    import shutil

    total, used, _ = shutil.disk_usage(path)
    if total <= 0:
        return 0.0
    return round(100.0 * used / total, 1)
