from __future__ import annotations

import logging
import sqlite3
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from bot.policy.types import WorkflowQoSClass

logger = logging.getLogger(__name__)

_PRIORITY_ORDER = (
    WorkflowQoSClass.BREAKING.value,
    WorkflowQoSClass.PUBLISH.value,
    WorkflowQoSClass.DIGEST.value,
    WorkflowQoSClass.ENRICHMENT.value,
    WorkflowQoSClass.MEDIA.value,
    WorkflowQoSClass.FEDERATION.value,
    WorkflowQoSClass.ANALYTICS.value,
    WorkflowQoSClass.BACKFILL.value,
)

_LATENCY_BUDGET_MS: dict[str, float] = {
    WorkflowQoSClass.BREAKING.value: 2000.0,
    WorkflowQoSClass.PUBLISH.value: 5000.0,
    WorkflowQoSClass.DIGEST.value: 120_000.0,
    WorkflowQoSClass.ENRICHMENT.value: 30_000.0,
    WorkflowQoSClass.ANALYTICS.value: 300_000.0,
}


@dataclass
class QoSSample:
    workflow_class: str
    latency_ms: float
    success: bool
    recorded_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
    )


class EditorialQoS:
    """Priority classes, SLA tracking, starvation prevention."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._wait_queues: dict[str, deque[float]] = {
            c: deque(maxlen=200) for c in _PRIORITY_ORDER
        }

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path, timeout=5.0)

    def record(self, sample: QoSSample) -> None:
        self._wait_queues.setdefault(sample.workflow_class, deque(maxlen=200)).append(
            sample.latency_ms,
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO qos_sla_samples (workflow_class, latency_ms, success, recorded_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    sample.workflow_class,
                    sample.latency_ms,
                    1 if sample.success else 0,
                    sample.recorded_at,
                ),
            )
            conn.commit()

    def priority_rank(self, workflow_class: str) -> int:
        try:
            return _PRIORITY_ORDER.index(workflow_class)
        except ValueError:
            return len(_PRIORITY_ORDER)

    def should_run(
        self,
        workflow_class: str,
        *,
        pressure: float,
        shed_classes: set[str],
    ) -> tuple[bool, str]:
        if workflow_class in shed_classes:
            return False, f"shed {workflow_class}"
        rank = self.priority_rank(workflow_class)
        if pressure > 0.85 and rank > self.priority_rank(WorkflowQoSClass.PUBLISH.value):
            return False, "overload: sub-publish priority paused"
        if pressure > 0.95 and rank > self.priority_rank(WorkflowQoSClass.BREAKING.value):
            return False, "critical overload: only breaking allowed"
        budget = _LATENCY_BUDGET_MS.get(workflow_class, 60_000.0)
        q = self._wait_queues.get(workflow_class)
        if q and len(q) >= 5:
            p95 = sorted(q)[int(len(q) * 0.95) - 1]
            if p95 > budget * 1.5:
                return False, f"latency budget exceeded p95={p95:.0f}ms"
        return True, "qos ok"

    def starvation_risk(self) -> list[str]:
        """Classes waiting disproportionately long vs breaking."""
        risks: list[str] = []
        breaking = self._wait_queues.get(WorkflowQoSClass.BREAKING.value, deque())
        break_avg = sum(breaking) / len(breaking) if breaking else 0
        for cls in _PRIORITY_ORDER[2:]:
            q = self._wait_queues.get(cls, deque())
            if len(q) < 3:
                continue
            avg = sum(q) / len(q)
            if avg > max(break_avg * 4, 10_000):
                risks.append(cls)
        return risks

    def observe_workflow(self, workflow_class: str, fn):
        """Decorator-style timing helper."""
        started = time.perf_counter()

        def _done(success: bool = True) -> None:
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            self.record(QoSSample(workflow_class, elapsed_ms, success))

        return _done
