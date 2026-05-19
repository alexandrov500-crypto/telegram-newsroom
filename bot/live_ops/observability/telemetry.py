from __future__ import annotations

import time
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator


@dataclass
class LiveOpsTelemetry:
    """Prometheus + in-memory counters for live operations."""

    _published: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    _dlq: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    def record_publish(self, event_type: str) -> None:
        self._published[event_type] += 1
        try:
            from bot.observability.metrics import record_live_ops_event

            record_live_ops_event(event_type, "published")
        except Exception:
            pass

    def record_dlq(self, event_type: str) -> None:
        self._dlq[event_type] += 1
        try:
            from bot.observability.metrics import record_live_ops_event

            record_live_ops_event(event_type, "dlq")
        except Exception:
            pass

    @contextmanager
    def time_cognition(self, *, story_id: int) -> Iterator[None]:
        start = time.perf_counter()
        try:
            yield
        finally:
            sec = time.perf_counter() - start
            try:
                from bot.observability.metrics import observe_cognition_duration

                observe_cognition_duration(sec)
            except Exception:
                pass
            self._published[f"cognition_timing:{story_id}"] = int(sec * 1000)

    @contextmanager
    def time_publish(self, *, channel_id: int) -> Iterator[None]:
        start = time.perf_counter()
        try:
            yield
        finally:
            sec = time.perf_counter() - start
            try:
                from bot.observability.metrics import observe_live_publish_latency

                observe_live_publish_latency(str(channel_id), sec)
            except Exception:
                pass

    def record_rollout_transition(self, from_stage: str, to_stage: str) -> None:
        try:
            from bot.observability.metrics import record_rollout_transition

            record_rollout_transition(from_stage, to_stage)
        except Exception:
            pass

    def record_operator_action(self, command: str) -> None:
        try:
            from bot.observability.metrics import record_operator_action

            record_operator_action(command)
        except Exception:
            pass

    def snapshot(self) -> dict[str, Any]:
        return {
            "published": dict(self._published),
            "dlq": dict(self._dlq),
        }
