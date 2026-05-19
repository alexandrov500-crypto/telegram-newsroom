from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from bot.week1.repository import Week1Repository


@dataclass
class SafeAdaptiveOptimization:
    repository: Week1Repository

    def propose_from_signals(self, signals: dict[str, Any]) -> list[str]:
        ids: list[str] = []
        queue = int(signals.get("queue_depth", 0))
        quality = float(signals.get("quality_avg", 0.8))

        if queue > 180:
            pid = self._add(
                category="pacing",
                recommendation="Reduce publish rate 15% for 6h",
                safety_score=0.88,
                blast_radius="low",
                detail={"queue_depth": queue},
            )
            ids.append(pid)
        if quality < 0.75:
            pid = self._add(
                category="quality",
                recommendation="Raise GA quality floor +0.03 until stable 24h",
                safety_score=0.82,
                blast_radius="medium",
                detail={"quality_avg": quality},
            )
            ids.append(pid)
        if float(signals.get("scaling_risk", 0)) > 0.5:
            pid = self._add(
                category="workers",
                recommendation="Rebalance cognition workers to hottest region",
                safety_score=0.75,
                blast_radius="medium",
                detail={"scaling_risk": signals.get("scaling_risk")},
            )
            ids.append(pid)
        return ids

    def _add(
        self,
        *,
        category: str,
        recommendation: str,
        safety_score: float,
        blast_radius: str,
        detail: dict[str, Any],
    ) -> str:
        pid = str(uuid.uuid4())[:12]
        self.repository.save_proposal(
            proposal_id=pid,
            category=category,
            recommendation=recommendation,
            safety_score=safety_score,
            blast_radius=blast_radius,
            detail=detail,
        )
        return pid

    def recommendations_html(self) -> str:
        rows = self.repository.pending_proposals()
        lines = ["<b>Adaptive recommendations</b> (approval required)"]
        for r in rows[:6]:
            lines.append(
                f"• [{r['category']}] {r['recommendation']}\n"
                f"  safety {r['safety_score']:.0%} · blast {r['blast_radius']}",
            )
        if not rows:
            lines.append("None pending — system stable")
        return "\n".join(lines)

    def safety_html(self) -> str:
        rows = self.repository.pending_proposals()
        if not rows:
            return "<b>Optimization safety</b> No pending proposals."
        unsafe = [r for r in rows if float(r["safety_score"]) < 0.8]
        return (
            f"<b>Optimization safety</b>\n"
            f"Pending: {len(rows)} · below 80% safety: {len(unsafe)}\n"
            "All changes require operator approval + rollback path."
        )
