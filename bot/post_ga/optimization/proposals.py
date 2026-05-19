from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from bot.post_ga.repository import PostGaRepository


@dataclass(frozen=True)
class OptimizationProposal:
    proposal_id: str
    category: str
    change: dict[str, Any]
    explain: str
    status: str = "pending"


@dataclass
class SafeSelfOptimizer:
    """Bounded proposals — explainable, reversible, operator approval."""

    repository: PostGaRepository
    auto_threshold: float = 0.05

    def propose(
        self,
        *,
        category: str,
        change: dict[str, Any],
        explain: str,
        impact_magnitude: float,
    ) -> OptimizationProposal | None:
        if impact_magnitude < self.auto_threshold:
            return None
        pid = str(uuid.uuid4())
        self.repository.save_proposal(
            proposal_id=pid,
            category=category,
            change=change,
            explain=explain,
        )
        return OptimizationProposal(pid, category, change, explain)

    def approve(self, proposal_id: str, operator_id: str) -> bool:
        pending = {p["proposal_id"] for p in self.repository.pending_proposals()}
        if proposal_id not in pending:
            return False
        self.repository.apply_proposal(proposal_id, operator_id)
        return True

    def list_pending_text(self) -> str:
        rows = self.repository.pending_proposals()
        if not rows:
            return "No pending optimization proposals."
        lines = ["<b>Optimization proposals</b>"]
        for r in rows[:6]:
            lines.append(
                f"• <code>{r['proposal_id'][:8]}</code> {r['category']}: "
                f"{r['explain_text'][:60]}",
            )
        lines.append("<i>Approve via ops workflow — all changes logged.</i>")
        return "\n".join(lines)

    def generate_from_signals(self, signals: dict[str, Any]) -> list[OptimizationProposal]:
        out: list[OptimizationProposal] = []
        pacing = signals.get("pacing_factor", 1.0)
        if pacing and pacing < 0.7:
            p = self.propose(
                category="pacing",
                change={"pacing_factor": 0.65},
                explain="Sustained low engagement — reduce publish rate 35%",
                impact_magnitude=0.15,
            )
            if p:
                out.append(p)
        if signals.get("queue_depth", 0) > 350:
            p = self.propose(
                category="queue",
                change={"ingest_throttle": True},
                explain="Queue pressure — throttle nonessential ingest",
                impact_magnitude=0.12,
            )
            if p:
                out.append(p)
        return out
