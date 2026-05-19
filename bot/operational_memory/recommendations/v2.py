from __future__ import annotations

import uuid
from typing import Any

from bot.operational_memory.repository import OperationalMemoryRepository


class OperationalRecommendationsV2:
    """Advisory recommendations grounded in incident history."""

    def __init__(self, repository: OperationalMemoryRepository) -> None:
        self.repository = repository

    def generate(
        self,
        *,
        signals: dict[str, Any],
        predictions: dict[str, dict[str, Any]],
        drift: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        proposals: list[dict[str, Any]] = []
        p15 = predictions.get("15m", {})
        if p15.get("degradation", 0) > 0.55:
            similar = [
                r["incident_type"]
                for r in self.repository.recurrent_types(min_count=2)[:3]
            ]
            pid = str(uuid.uuid4())[:8]
            text = "Reduce publish cadence 15% and enable queue backpressure (advisory)."
            self.repository.save_recommendation(
                proposal_id=pid,
                recommendation=text,
                expected_impact="Lower queue growth within 30m",
                blast_radius="publishing_throughput",
                rollback_safe=True,
                confidence=0.72,
                similar_incidents=similar,
            )
            proposals.append(
                {
                    "proposal_id": pid,
                    "recommendation": text,
                    "confidence": 0.72,
                    "similar": similar,
                },
            )
        systemic = [d for d, v in drift.items() if v.get("systemic")]
        if systemic and "latency" in systemic:
            pid = str(uuid.uuid4())[:8]
            text = "Review cognition timeout and source fetch parallelism (advisory)."
            self.repository.save_recommendation(
                proposal_id=pid,
                recommendation=text,
                expected_impact="Latency drift stabilization",
                blast_radius="editorial_pipeline",
                rollback_safe=True,
                confidence=0.68,
                similar_incidents=[],
            )
            proposals.append({"proposal_id": pid, "recommendation": text})
        return proposals

    def preventive_actions_html(self) -> str:
        pending = self.repository.pending_recommendations()
        lines = ["<b>Preventive actions</b> (advisory — approval required)"]
        for p in pending[:5]:
            lines.append(
                f"• [{p['proposal_id']}] {p['recommendation'][:80]}… "
                f"(conf {p['confidence']:.0%}, rollback-safe: {bool(p['rollback_safe'])})",
            )
        if len(lines) == 1:
            lines.append("No pending preventive actions.")
        return "\n".join(lines)
