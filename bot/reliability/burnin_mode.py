from __future__ import annotations

import logging
import resource
import sys
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BurnInDiagnostics:
    reliability_score: float
    memory_rss_mb: float
    queue_growth_rate: float
    duplicate_rate: float
    stuck_tasks: int
    verbose_notes: tuple[str, ...]

    def summary(self) -> str:
        lines = [
            f"<b>🔥 Burn-in diagnostics</b>",
            f"Reliability score: <b>{self.reliability_score:.2f}</b>",
            f"RSS memory: {self.memory_rss_mb:.1f} MB",
            f"Queue growth/h: {self.queue_growth_rate:.1f}",
            f"Dup rate: {self.duplicate_rate:.3f}",
            f"Stuck tasks: {self.stuck_tasks}",
        ]
        for n in self.verbose_notes[:4]:
            lines.append(f"• {n}")
        return "\n".join(lines)


class BurnInDiagnosticsRunner:
    """Aggressive pre-production diagnostics when RELIABILITY_BURNIN_MODE=true."""

    def __init__(self) -> None:
        self._queue_samples: list[tuple[float, int]] = []

    def record_queue(self, depth: int) -> None:
        import time

        self._queue_samples.append((time.monotonic(), depth))
        if len(self._queue_samples) > 120:
            self._queue_samples = self._queue_samples[-120:]

    def run(
        self,
        *,
        health_score: float,
        stalled_loops: list[str],
        duplicate_skips: int = 0,
        ingest_total: int = 0,
        ops_report: dict[str, Any] | None = None,
    ) -> BurnInDiagnostics:
        rss_mb = 0.0
        try:
            usage = resource.getrusage(resource.RUSAGE_SELF)
            rss_mb = usage.ru_maxrss / (1024 * 1024)
            if sys.platform == "darwin":
                rss_mb = usage.ru_maxrss / (1024 * 1024)
            else:
                rss_mb = usage.ru_maxrss / 1024.0
        except Exception:
            pass

        growth = 0.0
        if len(self._queue_samples) >= 2:
            t0, q0 = self._queue_samples[0]
            t1, q1 = self._queue_samples[-1]
            hours = max((t1 - t0) / 3600.0, 1 / 3600.0)
            growth = (q1 - q0) / hours

        dup_rate = duplicate_skips / max(ingest_total, 1)
        stuck = len(stalled_loops)
        score = health_score
        if growth > 50:
            score *= 0.85
        if dup_rate > 0.3:
            score *= 0.9
        if stuck:
            score *= 0.7

        notes: list[str] = []
        if ops_report:
            if ops_report.get("burnin_regressions"):
                notes.append(f"regressions={ops_report['burnin_regressions']}")
            notes.append(f"readiness={ops_report.get('operational_readiness', 'n/a')}")
        if stalled_loops:
            notes.append(f"stalled={','.join(stalled_loops[:4])}")

        logger.info(
            "event=burnin_diagnostics score=%.2f rss_mb=%.1f growth=%.1f dup=%.3f",
            score,
            rss_mb,
            growth,
            dup_rate,
        )
        return BurnInDiagnostics(
            reliability_score=score,
            memory_rss_mb=rss_mb,
            queue_growth_rate=growth,
            duplicate_rate=dup_rate,
            stuck_tasks=stuck,
            verbose_notes=tuple(notes),
        )
