"""
Rolling phase stats, light anomaly hints, trend warnings, operational summaries.
No external frameworks — in-process only.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import Counter, deque
from typing import Any

from app.config import Settings
from utils.metrics import avg_pipeline_duration_sec, snapshot
from utils.structured_log import log_event

_lock = threading.RLock()

_collect: deque[float] = deque(maxlen=64)
_openai: deque[float] = deque(maxlen=64)
_pipeline: deque[float] = deque(maxlen=64)
_publish: deque[float] = deque(maxlen=64)

_task_hist: deque[tuple[int, float]] = deque(maxlen=32)
_rss_hist: deque[tuple[int, float]] = deque(maxlen=32)
_raw_hist: deque[tuple[int, float]] = deque(maxlen=32)
_backlog_hist: deque[tuple[int, float]] = deque(maxlen=32)

_dup_skip_streak = 0

_editorial_summary_lens: deque[int] = deque(maxlen=128)
_editorial_source_counts: deque[int] = deque(maxlen=128)
_editorial_rep_ratios: deque[float] = deque(maxlen=128)
_content_hash_ring: deque[str] = deque(maxlen=32)


def configure_deque_maxlen(settings: Settings) -> None:
    n = max(5, min(settings.trend_ring_max_samples, 256))
    global _collect, _openai, _pipeline, _publish
    with _lock:

        def _reb(d: deque[float]) -> deque[float]:
            return deque(list(d), maxlen=n)

        _collect = _reb(_collect)
        _openai = _reb(_openai)
        _pipeline = _reb(_pipeline)
        _publish = _reb(_publish)


def _append(d: deque[float], v: float) -> None:
    if v > 0:
        d.append(v)


def record_collect_duration(sec: float) -> None:
    with _lock:
        _append(_collect, sec)


def record_openai_duration(sec: float) -> None:
    with _lock:
        _append(_openai, sec)


def record_pipeline_wall_sample(sec: float) -> None:
    with _lock:
        _append(_pipeline, sec)


def record_publish_duration(sec: float) -> None:
    with _lock:
        _append(_publish, sec)


def _avg(d: deque[float]) -> float | None:
    if len(d) < 2:
        return None
    return sum(d) / len(d)


def _warn_slow_phase(
    logger: logging.Logger,
    *,
    phase: str,
    current: float,
    rolling: deque[float],
    multiplier: float,
) -> None:
    avg = _avg(rolling)
    if avg is None or avg <= 0:
        return
    if current > avg * multiplier:
        log_event(
            logger,
            "ops.warn.phase_slower_than_rolling_avg",
            phase=phase,
            current_sec=round(current, 4),
            rolling_avg_sec=round(avg, 4),
            multiplier=multiplier,
        )


def check_phase_trends_after_tick(
    logger: logging.Logger,
    settings: Settings,
    tick: dict[str, float],
    wall_sec: float,
) -> None:
    mult = settings.trend_slow_multiplier
    if (c := tick.get("collect_sec")) is not None and c > 0:
        _warn_slow_phase(logger, phase="collect", current=c, rolling=_collect, multiplier=mult)
    if (o := tick.get("openai_sec")) is not None and o > 0:
        _warn_slow_phase(logger, phase="openai", current=o, rolling=_openai, multiplier=mult)
    if wall_sec > 0:
        _warn_slow_phase(logger, phase="pipeline_wall", current=wall_sec, rolling=_pipeline, multiplier=mult)


def check_publish_trend(logger: logging.Logger, settings: Settings, publish_sec: float) -> None:
    if publish_sec <= 0:
        return
    _warn_slow_phase(
        logger,
        phase="publish",
        current=publish_sec,
        rolling=_publish,
        multiplier=settings.trend_publish_slow_multiplier,
    )


def record_diagnostics_trend(
    logger: logging.Logger,
    settings: Settings,
    *,
    tasks: int,
    rss: int | None,
    raw_posts: int,
    backlog_unprocessed: int,
) -> None:
    now = time.monotonic()
    window = max(3, min(settings.memory_trend_window, 32))
    with _lock:
        _task_hist.append((tasks, now))
        if rss is not None:
            _rss_hist.append((rss, now))
        if raw_posts >= 0:
            _raw_hist.append((raw_posts, now))
        if backlog_unprocessed >= 0:
            _backlog_hist.append((backlog_unprocessed, now))

        def _monotonic_warn(name: str, hist: deque[tuple[int, float]]) -> None:
            if len(hist) < window:
                return
            recent = list(hist)[-window:]
            vals = [v for v, _ in recent]
            if len(vals) < window:
                return
            if all(vals[i] < vals[i + 1] for i in range(len(vals) - 1)):
                log_event(
                    logger,
                    "ops.warn.monotonic_growth",
                    series=name,
                    window=window,
                    first=vals[0],
                    last=vals[-1],
                    delta=vals[-1] - vals[0],
                )

        if settings.warn_task_count_trend:
            _monotonic_warn("asyncio_tasks", _task_hist)
        if settings.warn_rss_trend and rss is not None:
            _monotonic_warn("rss_bytes", _rss_hist)
        if settings.warn_raw_posts_trend:
            _monotonic_warn("raw_posts_total", _raw_hist)
        if settings.warn_backlog_trend:
            _monotonic_warn("raw_posts_unprocessed", _backlog_hist)


def record_duplicate_skip(logger: logging.Logger, settings: Settings) -> None:
    global _dup_skip_streak
    with _lock:
        _dup_skip_streak += 1
        streak = _dup_skip_streak
    if streak > 0 and streak % settings.anomaly_duplicate_skip_streak == 0:
        log_event(
            logger,
            "ops.warn.duplicate_skip_streak",
            streak=streak,
            threshold=settings.anomaly_duplicate_skip_streak,
        )


def reset_duplicate_skip_streak() -> None:
    global _dup_skip_streak
    with _lock:
        _dup_skip_streak = 0


def record_editorial_draft_sample(
    *,
    summary_len: int,
    source_count: int,
    content_hash: str,
    repetition_bigram_ratio: float,
) -> None:
    """Rolling editorial observability (averages + duplicate hash hints)."""
    lg = logging.getLogger(__name__)
    with _lock:
        _editorial_summary_lens.append(max(0, summary_len))
        _editorial_source_counts.append(max(0, source_count))
        _editorial_rep_ratios.append(max(0.0, min(1.0, repetition_bigram_ratio)))
        hp = (content_hash or "")[:20]
        if hp:
            _content_hash_ring.append(hp)
            if len(_content_hash_ring) >= 6:
                c_full = Counter(_content_hash_ring)
                if c_full[hp] == 3:
                    log_event(
                        lg,
                        "quality.warn.duplicate_summary_pattern",
                        window=len(_content_hash_ring),
                        repeats_for_hash_prefix=3,
                        hash_prefix=hp,
                    )


def _editorial_rollup_dict() -> dict[str, Any]:
    with _lock:
        if len(_editorial_summary_lens) < 2:
            return {}
        def _mean(d: deque[float] | deque[int]) -> float:
            return sum(d) / len(d) if d else 0.0

        rep_mean = _mean(_editorial_rep_ratios) if _editorial_rep_ratios else None
        return {
            "editorial_avg_summary_len": round(_mean(_editorial_summary_lens), 1),
            "editorial_avg_source_count": round(_mean(_editorial_source_counts), 2),
            "editorial_avg_repetition_bigram_ratio": round(rep_mean, 4) if rep_mean is not None else None,
            "editorial_sample_count": len(_editorial_summary_lens),
        }


def log_retention_db_effect(
    logger: logging.Logger,
    *,
    db_bytes_before: int | None,
    db_bytes_after: int | None,
    deleted_raw: int,
    deleted_drafts: int,
) -> None:
    if deleted_raw == 0 and deleted_drafts == 0:
        return
    log_event(
        logger,
        "sqlite.retention_effectiveness",
        deleted_raw=deleted_raw,
        deleted_drafts=deleted_drafts,
        db_bytes_before=db_bytes_before,
        db_bytes_after=db_bytes_after,
    )
    if (
        db_bytes_before is not None
        and db_bytes_after is not None
        and db_bytes_after >= db_bytes_before
        and (deleted_raw + deleted_drafts) > 0
    ):
        log_event(
            logger,
            "ops.warn.retention_no_db_shrink",
            db_bytes_before=db_bytes_before,
            db_bytes_after=db_bytes_after,
            deleted_raw=deleted_raw,
            deleted_drafts=deleted_drafts,
        )


def log_sqlite_files(logger: logging.Logger, *, db_bytes: int | None, wal_bytes: int | None) -> None:
    log_event(logger, "sqlite.files_snapshot", db_file_bytes=db_bytes, wal_file_bytes=wal_bytes)


def check_tick_anomalies(
    logger: logging.Logger,
    settings: Settings,
    *,
    wall_sec: float,
    cluster_size: int,
    asyncio_tasks: int,
    rss_bytes: int | None,
) -> None:
    avg_p = avg_pipeline_duration_sec()
    slow_mult = settings.anomaly_pipeline_slow_vs_avg_multiplier
    abs_slow = settings.anomaly_pipeline_slow_abs_sec
    if wall_sec > abs_slow:
        if avg_p is None or wall_sec > avg_p * slow_mult:
            log_event(
                logger,
                "ops.warn.pipeline_slow",
                wall_sec=round(wall_sec, 3),
                avg_pipeline_sec=round(avg_p, 3) if avg_p is not None else None,
                abs_threshold=abs_slow,
                vs_avg_multiplier=slow_mult,
            )

    lim = max(
        settings.min_raw_posts_for_ai,
        int(settings.max_cluster_posts * settings.anomaly_cluster_size_ratio),
    )
    if cluster_size > 0 and cluster_size >= lim:
        log_event(
            logger,
            "ops.warn.large_cluster",
            cluster_size=cluster_size,
            warn_at_least=lim,
            max_cluster_posts=settings.max_cluster_posts,
        )

    if settings.anomaly_asyncio_tasks_warn > 0 and asyncio_tasks >= settings.anomaly_asyncio_tasks_warn:
        log_event(
            logger,
            "ops.warn.asyncio_task_count",
            tasks=asyncio_tasks,
            threshold=settings.anomaly_asyncio_tasks_warn,
        )

    if (
        settings.anomaly_memory_rss_bytes_warn > 0
        and rss_bytes is not None
        and rss_bytes >= settings.anomaly_memory_rss_bytes_warn
    ):
        log_event(
            logger,
            "ops.warn.memory_rss",
            rss_bytes=rss_bytes,
            threshold=settings.anomaly_memory_rss_bytes_warn,
        )


def log_openai_failure_burst(logger: logging.Logger, settings: Settings, delta: int) -> None:
    if delta >= settings.anomaly_openai_failures_burst_delta:
        log_event(
            logger,
            "ops.warn.openai_failures_burst",
            failures_since_last_diag=delta,
            threshold=settings.anomaly_openai_failures_burst_delta,
        )


def log_telethon_reconnect_burst(logger: logging.Logger, settings: Settings, delta: int) -> None:
    if delta >= settings.anomaly_telethon_reconnect_burst:
        log_event(
            logger,
            "ops.warn.telethon_reconnect_burst",
            reconnects_since_last_diag=delta,
            threshold=settings.anomaly_telethon_reconnect_burst,
        )


def log_operational_summary(logger: logging.Logger, settings: Settings) -> None:
    snap = snapshot()
    avg = avg_pipeline_duration_sec()
    rss = None
    dbs = None
    up = None
    try:
        from utils.diagnostics import db_file_size_bytes, process_uptime_sec, rss_bytes_best_effort

        rss = rss_bytes_best_effort()
        dbs = db_file_size_bytes(settings)
        up = round(process_uptime_sec(), 1)
    except Exception:
        pass

    log_event(
        logger,
        "ops.report.summary",
        uptime_sec=up,
        posts_collected=snap.get("posts_collected", 0),
        drafts_generated=snap.get("drafts_generated", 0),
        publishes=snap.get("publishes", 0),
        skipped_duplicates=snap.get("skipped_duplicates", 0),
        openai_failures=snap.get("openai_failures", 0),
        retries=snap.get("openai_retries", 0),
        avg_pipeline_duration_sec=round(avg, 4) if avg is not None else None,
        rss_bytes=rss,
        db_file_bytes=dbs,
        telethon_reconnects=snap.get("telethon_reconnects", 0),
        telegram_api_failures=snap.get("telegram_api_failures", 0),
        publish_retries=snap.get("publish_retries", 0),
        admin_notify_failures=snap.get("admin_notify_failures", 0),
        **_editorial_rollup_dict(),
    )


def export_tick_timing_statistics() -> dict[str, Any]:
    """Bounded copies of rolling phase timing samples (for dumps / introspection)."""
    with _lock:
        return {
            "schema_version": 1,
            "collect_sec_samples": [round(x, 6) for x in _collect],
            "openai_sec_samples": [round(x, 6) for x in _openai],
            "pipeline_wall_sec_samples": [round(x, 6) for x in _pipeline],
            "publish_sec_samples": [round(x, 6) for x in _publish],
            "sample_counts": {
                "collect": len(_collect),
                "openai": len(_openai),
                "pipeline_wall": len(_pipeline),
                "publish": len(_publish),
            },
        }


def get_runtime_snapshot(settings: Settings) -> dict[str, Any]:
    """
    Lightweight JSON-serializable runtime view (no network, no OpenAI).
    Safe to call from health tooling or tests without running the scheduler loop.
    """
    from scheduler.runtime_context import get_pipeline_context
    from utils.diagnostics import asyncio_task_count, process_uptime_sec
    from utils.metrics import export_snapshot
    from utils.runtime_events import get_recent_runtime_events

    ctx = get_pipeline_context()
    tick: dict[str, Any] = {}
    sched: dict[str, Any] = {}
    if ctx is not None:
        tick = dict(ctx.tick_timings)
        sched = {
            "tick_in_progress": bool(ctx.tick_in_progress),
            "last_cluster_size": int(ctx.last_cluster_size),
            "last_scheduler_wall_sec": round(float(ctx.last_scheduler_wall_sec), 4),
            "duplicate_skipped_this_tick": bool(ctx.duplicate_skipped_this_tick),
        }

    metrics = export_snapshot()
    ctr = {str(k): int(v or 0) for k, v in (metrics.get("counters") or {}).items()}
    from utils.editorial_analytics import export_editorial_analytics

    ed = export_editorial_analytics(ctr)
    roll = _editorial_rollup_dict()
    dup_intel = {
        "duplicate_skip_rate": ed.get("duplicate_skip_rate"),
        "skipped_duplicates_total": ctr.get("skipped_duplicates", 0),
        "editorial_avg_repetition_bigram_ratio": roll.get("editorial_avg_repetition_bigram_ratio"),
    }
    events = get_recent_runtime_events(48)
    brk_n = sum(
        1
        for e in (events or [])
        if isinstance(e, dict) and str(e.get("kind") or "") == "draft_breaking_signal"
    )
    return {
        "schema_version": 1,
        "uptime_sec": round(process_uptime_sec(), 3),
        "asyncio_tasks": int(asyncio_task_count()),
        "metrics": metrics,
        "pipeline_failures_total": int(metrics["counters"].get("openai_failures", 0)),
        "retry_events_total": int(metrics["counters"].get("openai_retries", 0)),
        "posts_collected_total": int(metrics["counters"].get("posts_collected", 0)),
        "drafts_generated_total": int(metrics["counters"].get("drafts_generated", 0)),
        "drafts_created_total": int(metrics["counters"].get("drafts_created", 0)),
        "drafts_approved_total": int(metrics["counters"].get("drafts_approved", 0)),
        "drafts_rejected_total": int(metrics["counters"].get("drafts_rejected", 0)),
        "drafts_published_total": int(metrics["counters"].get("drafts_published", 0)),
        "publish_failures_total": int(metrics["counters"].get("publish_failures", 0)),
        "draft_edits_total": int(metrics["counters"].get("draft_edits", 0)),
        "scheduled_publish_fired_total": int(metrics["counters"].get("scheduled_publish_fired", 0)),
        "editorial_analytics": ed,
        "duplicate_intelligence": dup_intel,
        "editorial_intelligence": {
            "breaking_runtime_events_recent": int(brk_n),
            "editorial_breaking_detected_total": int(ctr.get("editorial_breaking_detected", 0)),
        },
        "scheduler": sched,
        "tick_timings_last": tick,
        "tick_timing_statistics": export_tick_timing_statistics(),
        "recent_runtime_events": get_recent_runtime_events(24),
        "pipeline_interval_minutes": int(settings.pipeline_interval_minutes),
        "soak_test": bool(settings.soak_test),
        "dry_run": bool(settings.dry_run),
    }
