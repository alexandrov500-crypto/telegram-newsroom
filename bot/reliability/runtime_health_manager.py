from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from bot.observability.loop_registry import LoopHeartbeatRegistry, get_loop_registry
from bot.reliability.settings import ReliabilitySettings
from bot.reliability.types import HealthState, SubsystemHealth, SubsystemName, RuntimeHealthSnapshot, PublishMode

logger = logging.getLogger(__name__)


@dataclass
class _SubsystemProbe:
    last_ok_monotonic: float = field(default_factory=time.monotonic)
    errors: deque[float] = field(default_factory=lambda: deque(maxlen=500))
    retries: deque[float] = field(default_factory=lambda: deque(maxlen=500))
    latency_ms: float = 0.0
    detail: str = "ok"
    metadata: dict[str, Any] = field(default_factory=dict)


class RuntimeHealthManager:
    """Centralized runtime health: heartbeats, scores, degraded detection."""

    def __init__(
        self,
        settings: ReliabilitySettings,
        *,
        loop_registry: LoopHeartbeatRegistry | None = None,
        queue_depth_fn: Callable[[], int] | None = None,
        publish_mode_fn: Callable[[], PublishMode] | None = None,
        startup_time: datetime | None = None,
    ) -> None:
        self._settings = settings
        self._loops = loop_registry or get_loop_registry()
        self._queue_depth_fn = queue_depth_fn or (lambda: 0)
        self._publish_mode_fn = publish_mode_fn or (lambda: PublishMode.SHADOW)
        self._startup = startup_time or datetime.now(timezone.utc)
        self._probes: dict[SubsystemName, _SubsystemProbe] = {
            s: _SubsystemProbe() for s in SubsystemName
        }
        self._last_snapshot: RuntimeHealthSnapshot | None = None

    def heartbeat(
        self,
        subsystem: SubsystemName,
        *,
        ok: bool = True,
        latency_ms: float | None = None,
        detail: str = "ok",
        retry: bool = False,
        **metadata: Any,
    ) -> None:
        probe = self._probes[subsystem]
        now = time.monotonic()
        if ok:
            probe.last_ok_monotonic = now
            probe.detail = detail
        else:
            probe.errors.append(now)
            probe.detail = detail
        if retry:
            probe.retries.append(now)
        if latency_ms is not None:
            probe.latency_ms = latency_ms
        if metadata:
            probe.metadata.update(metadata)

    def record_error(self, subsystem: SubsystemName, detail: str) -> None:
        self.heartbeat(subsystem, ok=False, detail=detail)

    def _count_recent(self, times: deque[float]) -> int:
        cutoff = time.monotonic() - self._settings.error_window_sec
        return sum(1 for t in times if t >= cutoff)

    def _subsystem_state(
        self,
        name: SubsystemName,
        *,
        stall_names: frozenset[str],
    ) -> SubsystemHealth:
        probe = self._probes[name]
        age = time.monotonic() - probe.last_ok_monotonic
        err_h = self._count_recent(probe.errors)
        ret_h = self._count_recent(probe.retries)
        err_rate = err_h / max(self._settings.error_window_sec / 3600.0, 1 / 3600.0)

        score = 1.0
        if age > 600:
            score -= 0.5
        elif age > 180:
            score -= 0.25
        score -= min(0.4, err_h * 0.05)
        score = max(0.0, min(1.0, score))

        stalled = False
        if name == SubsystemName.INGEST and "rss-ingestion" in stall_names:
            stalled = True
        if name == SubsystemName.COGNITION and (
            "cognitive-runtime" in stall_names or "federated-cognitive-mesh" in stall_names
        ):
            stalled = True
        if name == SubsystemName.SCHEDULER and "operations-platform" in stall_names:
            stalled = True

        if stalled or score < 0.35:
            state = HealthState.FAILED
        elif score < 0.55 or err_h >= 10:
            state = HealthState.CRITICAL
        elif score < 0.75 or err_h >= 3:
            state = HealthState.DEGRADED
        else:
            state = HealthState.HEALTHY

        return SubsystemHealth(
            name=name,
            state=state,
            score=score,
            last_heartbeat_sec=age,
            error_rate=err_rate,
            retries_hour=ret_h,
            detail=probe.detail if not stalled else f"stalled ({probe.detail})",
            metadata=dict(probe.metadata),
        )

    def probe(self) -> RuntimeHealthSnapshot:
        stalled = frozenset(self._loops.watchdog_stalled_names())
        subs = tuple(
            self._subsystem_state(s, stall_names=stalled) for s in SubsystemName
        )
        queue = int(self._queue_depth_fn())
        errors_h = sum(s.retries_hour + int(s.error_rate * 10) for s in subs)
        retries_h = sum(s.retries_hour for s in subs)

        scores = [s.score for s in subs]
        health_score = sum(scores) / max(len(scores), 1)
        if queue > self._settings.publish_max_queue_depth:
            health_score *= 0.7

        rank = {
            HealthState.HEALTHY: 0,
            HealthState.DEGRADED: 1,
            HealthState.CRITICAL: 2,
            HealthState.FAILED: 3,
        }
        worst_state = HealthState.HEALTHY
        for s in subs:
            if rank[s.state] > rank[worst_state]:
                worst_state = s.state

        if health_score < 0.4:
            worst_state = HealthState.FAILED
        elif health_score < 0.6 and rank[worst_state] < rank[HealthState.CRITICAL]:
            worst_state = HealthState.CRITICAL
        elif health_score < 0.8 and rank[worst_state] < rank[HealthState.DEGRADED]:
            worst_state = HealthState.DEGRADED

        stuck = bool(stalled) or queue > self._settings.publish_max_queue_depth * 2
        uptime = (datetime.now(timezone.utc) - self._startup).total_seconds()
        snap = RuntimeHealthSnapshot(
            overall_state=worst_state,
            health_score=health_score,
            degraded_mode=worst_state != HealthState.HEALTHY,
            subsystems=subs,
            queue_depth=queue,
            errors_per_hour=float(errors_h),
            retries_per_hour=retries_h,
            stuck_pipeline=stuck,
            publish_mode=self._publish_mode_fn(),
            uptime_sec=uptime,
        )
        self._last_snapshot = snap
        try:
            from bot.observability.metrics import set_runtime_health_score

            set_runtime_health_score(health_score)
        except Exception:
            pass
        return snap

    @property
    def last_snapshot(self) -> RuntimeHealthSnapshot | None:
        return self._last_snapshot

    def ingest_from_registry(self, registry: Any) -> None:
        """Pull RSS/Telegram cycle timestamps from ObservabilityRegistry."""
        try:
            from datetime import datetime, timezone

            now = datetime.now(timezone.utc)
            rss_at = getattr(registry, "last_rss_cycle_at", None)
            tg_at = getattr(registry, "last_telegram_cycle_at", None)
            rss_age = (now - rss_at).total_seconds() if rss_at else 9999.0
            tg_age = (now - tg_at).total_seconds() if tg_at else 9999.0
            if getattr(registry, "rss_ingestion_running", False) and rss_age < 900:
                self.heartbeat(
                    SubsystemName.INGEST,
                    ok=True,
                    detail=f"rss_age={rss_age:.0f}s",
                )
            elif getattr(registry, "rss_ingestion_running", False):
                self.record_error(SubsystemName.INGEST, f"rss_stale age={rss_age:.0f}s")
            if getattr(registry, "telegram_ingestion_running", False):
                if tg_age < 1200:
                    self.heartbeat(
                        SubsystemName.TELEGRAM_API,
                        ok=True,
                        detail=f"tg_age={tg_age:.0f}s",
                    )
                else:
                    self.record_error(
                        SubsystemName.TELEGRAM_API,
                        f"telegram_stale age={tg_age:.0f}s",
                    )
            lag = float(getattr(registry, "event_loop_lag_sec", 0.0))
            if lag > 2.0:
                self.record_error(
                    SubsystemName.SCHEDULER,
                    f"event_loop_lag={lag:.2f}s",
                )
        except Exception as exc:
            logger.debug("event=health_registry_ingest_failed error=%s", exc)
