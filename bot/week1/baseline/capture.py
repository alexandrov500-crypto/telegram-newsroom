from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from bot.week1.repository import Week1Repository


_BASELINE_DOMAINS = (
    "runtime",
    "traffic",
    "quality",
    "queue",
    "cognition",
    "operator_load",
)


@dataclass
class ProductionBaselineCapture:
    repository: Week1Repository

    def capture_all(self, signals: dict[str, Any]) -> dict[str, dict[str, Any]]:
        if not self.repository.get_state():
            from datetime import datetime, timezone

            self.repository.init_state(
                week_start_at=datetime.now(timezone.utc).isoformat(),
            )
        snapshots = {
            "runtime": {
                "rollout_stage": signals.get("rollout_stage"),
                "worker_health": signals.get("worker_health", 0.9),
            },
            "traffic": {
                "queue_depth": signals.get("queue_depth", 0),
                "publish_pressure": signals.get("publish_pressure", 0),
            },
            "quality": {
                "quality_avg": signals.get("quality_avg", 0.8),
                "engagement_quality": signals.get("engagement_quality", 0.75),
            },
            "queue": {"queue_depth": signals.get("queue_depth", 0)},
            "cognition": {
                "cognition_latency_ms": signals.get("cognition_latency_ms", 0),
                "quality_avg": signals.get("quality_avg", 0.8),
            },
            "operator_load": {
                "operator_attention": signals.get("operator_attention", 0.5),
            },
        }
        for domain, snap in snapshots.items():
            self.repository.save_baseline(domain, snap)
        self.repository.mark_baseline_captured()
        return snapshots

    def drift(self, domain: str, current: dict[str, Any]) -> dict[str, float]:
        base = self.repository.get_baseline(domain) or {}
        drift: dict[str, float] = {}
        for k, v in current.items():
            if k not in base:
                continue
            try:
                drift[k] = float(v) - float(base[k])
            except (TypeError, ValueError):
                continue
        return drift

    def status_html(self) -> str:
        bases = self.repository.all_baselines()
        st = self.repository.get_state() or {}
        lines = [
            "<b>Production baselines</b>",
            f"Captured: {'yes' if st.get('baseline_captured') else 'pending'}",
            f"Domains: {len(bases)}/{len(_BASELINE_DOMAINS)}",
        ]
        for d in sorted(bases.keys()):
            lines.append(f"• {d}")
        return "\n".join(lines)
