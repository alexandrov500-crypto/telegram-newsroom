from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bot.operations.repository import OperationsRepository


@dataclass(frozen=True)
class LongevityReport:
    period: str
    metrics: dict[str, Any]
    markdown: str


class LongevityReportGenerator:
    """24h / 72h / 7d runtime validation reports."""

    PERIODS = ("24h", "72h", "7d")

    def __init__(self, repository: OperationsRepository) -> None:
        self._repo = repository

    def generate(self, period: str, *, signals: dict[str, Any]) -> LongevityReport:
        samples = self._repo.burnin_samples_for_period(period)
        metrics = {
            "period": period,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "sample_count": len(samples),
            "memory_mb_peak": max((s.get("memory_mb", 0) for s in samples), default=0),
            "queue_backlog_peak": max((s.get("queue_backlog", 0) for s in samples), default=0),
            "contradiction_peak": max(
                (s.get("open_contradictions", 0) for s in samples), default=0,
            ),
            "mesh_health_min": min((s.get("mesh_health", 1) for s in samples), default=1.0),
            "replay_divergence_max": max(
                (s.get("replay_divergence", 0) for s in samples), default=0,
            ),
            "current_signals": signals,
        }
        md = self._markdown(metrics)
        self._repo.save_longevity_snapshot(period, metrics)
        return LongevityReport(period=period, metrics=metrics, markdown=md)

    def write_artifact(self, report: LongevityReport, base_dir: Path | None = None) -> Path:
        base = base_dir or Path("artifacts/operations")
        base.mkdir(parents=True, exist_ok=True)
        path = base / f"longevity_{report.period}.json"
        path.write_text(json.dumps(report.metrics, indent=2), encoding="utf-8")
        return path

    @staticmethod
    def _markdown(metrics: dict[str, Any]) -> str:
        return "\n".join(
            [
                f"# Runtime longevity — {metrics['period']}",
                "",
                f"Samples: **{metrics['sample_count']}**",
                f"Memory peak: **{metrics['memory_mb_peak']:.0f} MB**",
                f"Queue peak: **{metrics['queue_backlog_peak']}**",
                f"Contradiction peak: **{metrics['contradiction_peak']}**",
                f"Mesh min: **{metrics['mesh_health_min']:.2f}**",
                f"Replay divergence max: **{metrics['replay_divergence_max']:.4f}**",
            ]
        )
