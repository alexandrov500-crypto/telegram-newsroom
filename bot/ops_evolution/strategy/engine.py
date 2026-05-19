from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from bot.ops_evolution.repository import OpsEvolutionRepository


@dataclass
class StrategicOptimizationEngine:
    """Long-horizon proposals — explainable, approval-required."""

    repository: OpsEvolutionRepository

    def analyze_signals(self, signals: dict[str, Any]) -> list[str]:
        proposals: list[str] = []
        if signals.get("queue_depth", 0) > 300:
            pid = self.repository.save_strategy_proposal(
                domain="scalability",
                title="Chronic queue pressure — add cognition worker capacity",
                impact=0.15,
                confidence=0.72,
                tradeoffs=["higher_cost", "faster_drain"],
                explain="Sustained queue depth suggests ingest/cognition imbalance.",
            )
            proposals.append(pid)
        if signals.get("quality_avg", 1.0) < 0.7:
            pid = self.repository.save_strategy_proposal(
                domain="quality",
                title="Source portfolio review — prune weak feeds",
                impact=0.12,
                confidence=0.68,
                tradeoffs=["fewer_stories", "higher_trust"],
                explain="Rolling quality below threshold — strategic source audit recommended.",
            )
            proposals.append(pid)
        if signals.get("ai_spend_ratio", 0) > 0.85:
            pid = self.repository.save_strategy_proposal(
                domain="economics",
                title="Cognition path cost optimization",
                impact=0.1,
                confidence=0.75,
                tradeoffs=["shorter_summaries", "lower_latency_cost"],
                explain="Spend approaching cap — tune model tier or batch cognition.",
            )
            proposals.append(pid)
        return proposals

    def list_pending_text(self) -> str:
        rows = self.repository.pending_strategies()
        if not rows:
            return "No strategic optimizations pending."
        lines = ["<b>Strategic optimizations</b>"]
        for r in rows[:8]:
            lines.append(
                f"• <code>{r['proposal_id'][:8]}</code> [{r['domain']}] "
                f"{r['title'][:50]}…",
            )
            lines.append(
                f"  impact {r['impact_estimate']:.0%} · conf {r['confidence']:.0%}",
            )
        lines.append("<i>Approval required — no auto-apply.</i>")
        return "\n".join(lines)

    def impact_text(self, proposal_id: str) -> str:
        rows = self.repository.pending_strategies()
        match = next((r for r in rows if r["proposal_id"].startswith(proposal_id)), None)
        if not match:
            return f"No proposal matching <code>{proposal_id}</code>"
        tradeoffs = match.get("tradeoffs_json", "[]")
        return (
            f"<b>Impact analysis</b>\n"
            f"{match['title']}\n"
            f"Impact est: {match['impact_estimate']:.0%}\n"
            f"Confidence: {match['confidence']:.0%}\n"
            f"Tradeoffs: {tradeoffs}\n"
            f"{match['explain_text']}"
        )
