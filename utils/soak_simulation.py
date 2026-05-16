"""
Controlled operational soak simulation (async, lightweight).

Synthetic metrics + timeline + suppression bursts — no Locust/K6.
Use short ``max_ticks`` or ``duration_sec`` in CI; longer runs via CLI.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Coroutine

from app.config import Settings
from dashboard.timeline import append_timeline_event
from editorial.drift_detection import append_drift_snapshot
from editorial.events import append_event_history
from editorial.suppression_memory import bump_duplicate_burst, duplicate_burst_count, record_suppression_ttl
from utils import metrics as metrics_mod
from utils.diagnostics import rss_bytes_best_effort


SoakProfileFn = Callable[[Settings, int, "SoakMetricsState"], Coroutine[Any, Any, None]]


@dataclass
class SoakMetricsState:
    """Synthetic queue depth (observability only; not the real job transport)."""

    sim_pending_depth: int = 0
    sim_publish_latency_ms: float = 50.0


@dataclass
class SoakSnapshot:
    tick: int
    monotonic_ts: float
    counters: dict[str, int]
    gauges: dict[str, float]
    rss_bytes: int | None
    timeline_event_count: int
    timeline_file_bytes: int
    suppression_entry_count: int
    duplicate_burst: int
    sim_pending_depth: int
    memory_rss_delta_from_start: int | None
    event_history_count: int = 0
    drift_snapshot_count: int = 0


@dataclass
class SoakRunResult:
    profile: str
    ticks: int
    duration_sec: float
    snapshots: list[SoakSnapshot] = field(default_factory=list)
    bounded_report: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def _timeline_counts(runtime_dir: str) -> tuple[int, int]:
    from editorial.intelligence_store import load_json, operational_timeline_path

    path = operational_timeline_path(runtime_dir)
    data = load_json(path, {"version": 1, "events": []})
    evs = data.get("events") or []
    n = len(evs) if isinstance(evs, list) else 0
    try:
        b = path.stat().st_size if path.is_file() else 0
    except OSError:
        b = 0
    return n, int(b)


def _suppression_entry_count(runtime_dir: str) -> int:
    from editorial.intelligence_store import load_json, suppression_state_path

    data = load_json(suppression_state_path(runtime_dir), {"version": 1, "entries": {}})
    ent = data.get("entries") or {}
    return len(ent) if isinstance(ent, dict) else 0


def _event_history_count(runtime_dir: str) -> int:
    from editorial.intelligence_store import event_history_path, load_json

    data = load_json(event_history_path(runtime_dir), {"version": 1, "events": []})
    ev = data.get("events") or []
    return len(ev) if isinstance(ev, list) else 0


def _drift_snapshot_count(runtime_dir: str) -> int:
    from editorial.intelligence_store import drift_snapshots_path, load_json

    data = load_json(drift_snapshots_path(runtime_dir), {"version": 1, "snapshots": []})
    s = data.get("snapshots") or []
    return len(s) if isinstance(s, list) else 0


async def _snap(
    settings: Settings,
    tick: int,
    *,
    state: SoakMetricsState,
    rss_start: int | None,
) -> SoakSnapshot:
    exp = metrics_mod.export_snapshot()
    tl_n, tl_b = _timeline_counts(settings.runtime_state_dir)
    rss = rss_bytes_best_effort()
    return SoakSnapshot(
        tick=tick,
        monotonic_ts=time.monotonic(),
        counters=dict(exp.get("counters") or {}),
        gauges=dict(exp.get("gauges") or {}),
        rss_bytes=rss,
        timeline_event_count=tl_n,
        timeline_file_bytes=tl_b,
        suppression_entry_count=_suppression_entry_count(settings.runtime_state_dir),
        duplicate_burst=duplicate_burst_count(settings.runtime_state_dir),
        sim_pending_depth=state.sim_pending_depth,
        memory_rss_delta_from_start=None if rss is None or rss_start is None else int(rss) - int(rss_start),
        event_history_count=_event_history_count(settings.runtime_state_dir),
        drift_snapshot_count=_drift_snapshot_count(settings.runtime_state_dir),
    )


async def _tick_low(settings: Settings, tick: int, st: SoakMetricsState) -> None:
    metrics_mod.inc("posts_collected", 1)
    metrics_mod.inc("clusters_created", 1)
    metrics_mod.set_gauge("ai_last_cluster_latency_sec", 0.8 + (tick % 3) * 0.1)
    st.sim_pending_depth = min(st.sim_pending_depth + 1, 8)
    append_timeline_event(settings.runtime_state_dir, "soak_low", {"tick": tick})
    await asyncio.sleep(0)


async def _tick_medium(settings: Settings, tick: int, st: SoakMetricsState) -> None:
    metrics_mod.inc("posts_collected", 3)
    metrics_mod.inc("drafts_generated", 2)
    metrics_mod.inc("drafts_created", 1)
    metrics_mod.set_gauge("ai_last_cluster_latency_sec", 4.0 + (tick % 5) * 0.4)
    st.sim_pending_depth = min(st.sim_pending_depth + 2, 40)
    append_event_history(
        settings.runtime_state_dir,
        fingerprint=f"soak_medium_{tick}",
        combined_text_excerpt=f"synthetic cluster tick={tick}",
    )
    for i in range(2):
        append_timeline_event(settings.runtime_state_dir, "soak_medium", {"tick": tick, "i": i})
    await asyncio.sleep(0)


async def _tick_burst(settings: Settings, tick: int, st: SoakMetricsState) -> None:
    metrics_mod.inc("posts_collected", 12)
    metrics_mod.inc("clusters_created", 5)
    metrics_mod.inc("drafts_generated", 4)
    metrics_mod.inc("publishes", 2)
    metrics_mod.inc("publish_retries", 1)
    metrics_mod.set_gauge("ai_last_cluster_latency_sec", 25.0 + (tick % 7))
    st.sim_pending_depth = min(st.sim_pending_depth + 15, 500)
    append_timeline_event(settings.runtime_state_dir, "soak_burst", {"tick": tick})
    append_drift_snapshot(
        settings.runtime_state_dir,
        {
            "acceptance_proxy": 0.52 + (tick % 5) * 0.01,
            "suppression_rate": 0.08,
            "avg_confidence": 0.41,
            "avg_headline_quality": 0.35,
            "manual_edit_rate": 0.02,
        },
    )
    await asyncio.sleep(0)


async def _tick_noisy_duplicate_storm(settings: Settings, tick: int, st: SoakMetricsState) -> None:
    metrics_mod.inc("posts_collected", 6)
    metrics_mod.inc("skipped_duplicates", 20)
    metrics_mod.inc("openai_retries", 2)
    bump_duplicate_burst(settings.runtime_state_dir, window_sec=3600.0)
    record_suppression_ttl(settings.runtime_state_dir, f"soak_dup_{tick % 50}", 120.0, reason="soak")
    metrics_mod.set_gauge("ai_last_cluster_latency_sec", 2.5)
    st.sim_pending_depth = min(st.sim_pending_depth + 5, 200)
    append_timeline_event(settings.runtime_state_dir, "soak_duplicate_storm", {"tick": tick})
    if tick % 4 == 0:
        metrics_mod.inc("drafts_published", 1)
        metrics_mod.record_pipeline_duration(0.4 + (tick % 3) * 0.05)
        from utils.editorial_analytics import record_moderation_publish_latency_sec

        record_moderation_publish_latency_sec(0.35 + (tick % 4) * 0.02)
    await asyncio.sleep(0)


PROFILE_HANDLERS: dict[str, SoakProfileFn] = {
    "low": _tick_low,
    "medium": _tick_medium,
    "burst": _tick_burst,
    "noisy_duplicate_storm": _tick_noisy_duplicate_storm,
}


def collect_bounded_state_report(settings: Settings, *, timeline_max_entries: int = 260) -> dict[str, Any]:
    """Post-run structural bounds + stale hints (JSON-serializable)."""
    from editorial.intelligence_store import drift_snapshots_path, event_history_path
    from utils.runtime_integrity import (
        validate_event_history,
        validate_operational_timeline,
        validate_suppression_state,
    )

    runtime_dir = settings.runtime_state_dir
    issues: list[str] = []
    issues.extend(validate_operational_timeline(runtime_dir))
    issues.extend(validate_suppression_state(runtime_dir))
    issues.extend(validate_event_history(runtime_dir))
    tl_n, tl_b = _timeline_counts(runtime_dir)
    if tl_n > timeline_max_entries:
        issues.append(f"timeline_events_exceed_soft_cap count={tl_n} cap={timeline_max_entries}")
    dup = duplicate_burst_count(runtime_dir)
    rss = rss_bytes_best_effort()
    exp = metrics_mod.export_snapshot()
    counters = exp.get("counters") or {}
    posts = int(counters.get("posts_collected") or 0)
    skipped = int(counters.get("skipped_duplicates") or 0)
    suppression_ratio = round(skipped / max(1, posts), 6) if posts else 0.0
    ev_n = _event_history_count(runtime_dir)
    drift_n = _drift_snapshot_count(runtime_dir)
    ev_b = drift_b = 0
    try:
        ev_p = event_history_path(runtime_dir)
        ev_b = int(ev_p.stat().st_size) if ev_p.is_file() else 0
    except OSError:
        ev_b = -1
    try:
        d_p = drift_snapshots_path(runtime_dir)
        drift_b = int(d_p.stat().st_size) if d_p.is_file() else 0
    except OSError:
        drift_b = -1
    return {
        "runtime_dir": runtime_dir,
        "timeline_events": tl_n,
        "timeline_file_bytes": tl_b,
        "duplicate_burst": dup,
        "suppression_entries": _suppression_entry_count(runtime_dir),
        "event_history_events": ev_n,
        "event_history_file_bytes": ev_b,
        "drift_snapshots": drift_n,
        "drift_snapshots_file_bytes": drift_b,
        "rss_bytes": rss,
        "suppression_ratio_posts": suppression_ratio,
        "integrity_issues": issues,
        "ok": len(issues) == 0,
    }


def evaluate_runtime_state_warnings(report: dict[str, Any], *, settings: Settings) -> list[str]:
    """Soft operational warnings from a bounded-state report (non-fatal)."""
    warns: list[str] = []
    lim = int(getattr(settings, "runtime_queue_pending_warn", 500))
    # soak stores peak sim depth in report if caller passes it
    sim = int(report.get("peak_sim_pending_depth") or 0)
    if sim > lim:
        warns.append(f"soak_peak_sim_pending_depth_high peak={sim} warn_threshold={lim}")
    rss = report.get("rss_bytes")
    rwarn = int(getattr(settings, "anomaly_memory_rss_bytes_warn", 0) or 0)
    if rwarn > 0 and rss is not None and int(rss) > rwarn:
        warns.append(f"rss_above_anomaly_threshold rss={rss} threshold={rwarn}")
    tbytes = int(report.get("timeline_file_bytes") or 0)
    if tbytes > 2_000_000:
        warns.append(f"timeline_json_large_bytes bytes={tbytes}")
    return warns


async def run_soak_simulation(
    settings: Settings,
    profile: str,
    *,
    duration_sec: float = 5.0,
    tick_interval_sec: float = 0.05,
    max_ticks: int | None = None,
    reset_metrics_at_start: bool = True,
) -> SoakRunResult:
    handler = PROFILE_HANDLERS.get(profile)
    if handler is None:
        raise ValueError(f"unknown soak profile {profile!r}; expected one of {sorted(PROFILE_HANDLERS)}")

    if reset_metrics_at_start:
        metrics_mod.reset_metrics()
        from utils.editorial_analytics import reset_editorial_analytics_for_tests

        reset_editorial_analytics_for_tests()

    rd = Path(settings.runtime_state_dir)
    rd.mkdir(parents=True, exist_ok=True)
    st = SoakMetricsState()
    rss_start = rss_bytes_best_effort()
    snaps: list[SoakSnapshot] = []
    t0 = time.monotonic()
    tick = 0
    peak_sim = 0
    while True:
        elapsed = time.monotonic() - t0
        if max_ticks is not None and tick >= max_ticks:
            break
        if max_ticks is None and elapsed >= duration_sec:
            break
        await handler(settings, tick, st)
        peak_sim = max(peak_sim, st.sim_pending_depth)
        snaps.append(await _snap(settings, tick, state=st, rss_start=rss_start))
        tick += 1
        if tick_interval_sec > 0:
            await asyncio.sleep(tick_interval_sec)

    bounded = collect_bounded_state_report(settings)
    bounded["peak_sim_pending_depth"] = peak_sim
    warns = evaluate_runtime_state_warnings(bounded, settings=settings)

    return SoakRunResult(
        profile=profile,
        ticks=tick,
        duration_sec=round(time.monotonic() - t0, 4),
        snapshots=snaps,
        bounded_report=bounded,
        warnings=warns,
    )


def soak_result_to_dict(result: SoakRunResult) -> dict[str, Any]:
    """JSON-friendly export (trim large snapshot lists via caller if needed)."""
    return {
        "profile": result.profile,
        "ticks": result.ticks,
        "duration_sec": result.duration_sec,
        "bounded_report": result.bounded_report,
        "warnings": result.warnings,
        "snapshots": [
            {
                "tick": s.tick,
                "monotonic_ts": s.monotonic_ts,
                "counters": s.counters,
                "gauges": s.gauges,
                "rss_bytes": s.rss_bytes,
                "timeline_event_count": s.timeline_event_count,
                "timeline_file_bytes": s.timeline_file_bytes,
                "suppression_entry_count": s.suppression_entry_count,
                "duplicate_burst": s.duplicate_burst,
                "sim_pending_depth": s.sim_pending_depth,
                "memory_rss_delta_from_start": s.memory_rss_delta_from_start,
                "event_history_count": s.event_history_count,
                "drift_snapshot_count": s.drift_snapshot_count,
            }
            for s in result.snapshots
        ],
    }
