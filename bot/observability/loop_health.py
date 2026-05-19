from __future__ import annotations

import logging
import os
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

WARN_ITER_SEC = 1.0
CRITICAL_ITER_SEC = 3.0


@dataclass
class LoopIterationStats:
    loop_name: str
    iteration_duration: float = 0.0
    feed_count: int = 0
    article_count: int = 0
    network_duration: float = 0.0
    db_write_duration: float = 0.0
    longest_feed_fetch: float = 0.0
    longest_feed_url: str = ""
    longest_parse: float = 0.0
    task_duration: float = 0.0
    openai_duration: float = 0.0
    decision_duration: float = 0.0
    publish_duration: float = 0.0
    sleep_duration: float = 0.0
    passive: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class LoopHealthTracker:
    rss_duration_sum: float = 0.0
    rss_duration_max: float = 0.0
    rss_samples: int = 0
    autonomous_duration_sum: float = 0.0
    autonomous_duration_max: float = 0.0
    autonomous_samples: int = 0
    stalled_loop_count: int = 0
    recovery_attempt_count: int = 0
    recovery_suppressed_count: int = 0
    last_rss: dict[str, Any] = field(default_factory=dict)
    last_autonomous: dict[str, Any] = field(default_factory=dict)
    recent_rss: deque[dict[str, Any]] = field(default_factory=lambda: deque(maxlen=24))
    recent_autonomous: deque[dict[str, Any]] = field(default_factory=lambda: deque(maxlen=24))


_tracker = LoopHealthTracker()


def get_loop_health() -> LoopHealthTracker:
    return _tracker


def _pilot_passive_autonomous() -> bool:
    try:
        from bot.runtime.profile import get_runtime_capabilities, loop_active

        caps = get_runtime_capabilities()
        if caps.profile.value == "minimal_pilot":
            return not loop_active(caps.autonomous_runtime)
    except Exception:
        pass
    if os.getenv("PILOT_AUTONOMOUS_PASSIVE", "").lower() in ("0", "false", "no"):
        return False
    if os.getenv("PILOT_AUTONOMOUS_PASSIVE", "").lower() in ("1", "true", "yes"):
        return True
    mode = os.getenv("LIVE_MODE", "").strip().lower()
    if mode in ("canary", "supervised_live", "shadow"):
        return True
    return os.getenv("APP_ENV", "").strip().lower() == "pilot"


def is_autonomous_passive_mode() -> bool:
    from bot.runtime.state import runtime_state

    if runtime_state.autonomous_passive:
        return True
    return _pilot_passive_autonomous()


def record_rss_iteration(stats: LoopIterationStats) -> None:
    t = _tracker
    t.rss_samples += 1
    t.rss_duration_sum += stats.iteration_duration
    t.rss_duration_max = max(t.rss_duration_max, stats.iteration_duration)
    payload = {
        "loop_name": stats.loop_name,
        "iteration_duration": round(stats.iteration_duration, 4),
        "feed_count": stats.feed_count,
        "article_count": stats.article_count,
        "network_duration": round(stats.network_duration, 4),
        "db_write_duration": round(stats.db_write_duration, 4),
        "longest_feed_fetch": round(stats.longest_feed_fetch, 4),
        "longest_feed_url": stats.longest_feed_url[:80],
    }
    t.last_rss = payload
    t.recent_rss.append(payload)
    level = _log_duration("rss-ingestion", stats.iteration_duration, payload)
    try:
        from bot.observability.metrics import set_rss_loop_health

        set_rss_loop_health(
            avg=t.rss_duration_sum / max(1, t.rss_samples),
            max_sec=t.rss_duration_max,
        )
    except Exception:
        pass
    if level == "critical":
        logger.critical("event=rss_ingestion_iteration %s", payload)
    elif level == "warning":
        logger.warning("event=rss_ingestion_iteration %s", payload)
    else:
        logger.info("event=rss_ingestion_iteration %s", payload)


def record_autonomous_iteration(stats: LoopIterationStats) -> None:
    t = _tracker
    t.autonomous_samples += 1
    t.autonomous_duration_sum += stats.task_duration
    t.autonomous_duration_max = max(t.autonomous_duration_max, stats.task_duration)
    payload = {
        "loop_name": stats.loop_name,
        "task_duration": round(stats.task_duration, 4),
        "openai_duration": round(stats.openai_duration, 4),
        "decision_duration": round(stats.decision_duration, 4),
        "publish_duration": round(stats.publish_duration, 4),
        "sleep_duration": round(stats.sleep_duration, 4),
        "passive": stats.passive,
        **stats.extra,
    }
    t.last_autonomous = payload
    t.recent_autonomous.append(payload)
    level = _log_duration("autonomous-runtime", stats.task_duration, payload)
    try:
        from bot.observability.metrics import set_autonomous_loop_health

        set_autonomous_loop_health(
            avg=t.autonomous_duration_sum / max(1, t.autonomous_samples),
            max_sec=t.autonomous_duration_max,
            passive=stats.passive,
        )
    except Exception:
        pass
    if level == "critical":
        logger.critical("event=autonomous_runtime_iteration %s", payload)
    elif level == "warning":
        logger.warning("event=autonomous_runtime_iteration %s", payload)


def record_stalled_loops(names: list[str]) -> None:
    if names:
        _tracker.stalled_loop_count += len(names)


def record_recovery_attempt(*, suppressed: bool = False) -> None:
    if suppressed:
        _tracker.recovery_suppressed_count += 1
    else:
        _tracker.recovery_attempt_count += 1


def snapshot() -> dict[str, Any]:
    t = _tracker
    rss_avg = t.rss_duration_sum / max(1, t.rss_samples)
    auto_avg = t.autonomous_duration_sum / max(1, t.autonomous_samples)
    recovery_rate = 0.0
    total = t.recovery_attempt_count + t.recovery_suppressed_count
    if total:
        recovery_rate = t.recovery_attempt_count / total
    return {
        "rss_loop_duration_avg": round(rss_avg, 4),
        "rss_loop_duration_max": round(t.rss_duration_max, 4),
        "autonomous_loop_duration_avg": round(auto_avg, 4),
        "autonomous_loop_duration_max": round(t.autonomous_duration_max, 4),
        "autonomous_passive": is_autonomous_passive_mode(),
        "stalled_loop_count": t.stalled_loop_count,
        "recovery_attempt_count": t.recovery_attempt_count,
        "recovery_suppressed_count": t.recovery_suppressed_count,
        "recovery_rate": round(recovery_rate, 4),
        "last_rss": dict(t.last_rss),
        "last_autonomous": dict(t.last_autonomous),
    }


def _log_duration(loop_name: str, duration_sec: float, payload: dict[str, Any]) -> str | None:
    if duration_sec >= CRITICAL_ITER_SEC:
        try:
            from bot.observability.metrics import record_slow_job

            record_slow_job(loop_name, duration_sec)
        except Exception:
            pass
        return "critical"
    if duration_sec >= WARN_ITER_SEC:
        try:
            from bot.observability.metrics import record_slow_job

            record_slow_job(loop_name, duration_sec)
        except Exception:
            pass
        return "warning"
    return None
