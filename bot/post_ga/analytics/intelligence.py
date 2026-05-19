from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class OperationalIntelligence:
    """Publish effectiveness, cost efficiency, weekly recommendations."""

    _publish_success: int = 0
    _publish_total: int = 0
    _latency_quality_pairs: list[tuple[float, float]] = field(default_factory=list)
    _rollback_count: int = 0

    def record_publish(self, *, success: bool, latency_sec: float, quality: float) -> None:
        self._publish_total += 1
        if success:
            self._publish_success += 1
        self._latency_quality_pairs.append((latency_sec, quality))
        if len(self._latency_quality_pairs) > 100:
            self._latency_quality_pairs = self._latency_quality_pairs[-100:]

    def record_rollback(self) -> None:
        self._rollback_count += 1

    def weekly_summary(self) -> dict[str, Any]:
        rate = self._publish_success / max(self._publish_total, 1)
        corr = 0.0
        if len(self._latency_quality_pairs) >= 5:
            lats = [p[0] for p in self._latency_quality_pairs]
            quals = [p[1] for p in self._latency_quality_pairs]
            mean_l = sum(lats) / len(lats)
            mean_q = sum(quals) / len(quals)
            num = sum((l - mean_l) * (q - mean_q) for l, q in self._latency_quality_pairs)
            den = (sum((l - mean_l) ** 2 for l in lats) * sum((q - mean_q) ** 2 for q in quals)) ** 0.5
            corr = num / den if den > 1e-6 else 0.0
        recs: list[str] = []
        if rate < 0.9:
            recs.append("investigate_publish_failures")
        if corr < -0.3:
            recs.append("cognition_latency_hurting_quality")
        if self._rollback_count > 2:
            recs.append("review_rollout_stability")
        return {
            "publish_effectiveness": round(rate, 3),
            "latency_quality_correlation": round(corr, 3),
            "rollbacks": self._rollback_count,
            "recommendations": recs,
        }

    def summary_text(self) -> str:
        w = self.weekly_summary()
        lines = [
            "<b>Ops intelligence</b>",
            f"Publish effectiveness {w['publish_effectiveness']:.0%}",
            f"Latency↔quality {w['latency_quality_correlation']:.2f}",
        ]
        for r in w.get("recommendations", [])[:3]:
            lines.append(f"→ {r}")
        return "\n".join(lines)
