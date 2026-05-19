from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class EvolutionExecutiveReport:
    def build(
        self,
        *,
        maturity_overall: float,
        sustainability: float,
        trust_trend: str,
        evolution_risk: float,
        autonomy_score: float,
        operator_attention: float,
        strategic_pending: int,
        weakest_domain: str,
        long_term_risks: list[str],
    ) -> str:
        m_emoji = "🟢" if maturity_overall >= 0.8 else "🟡" if maturity_overall >= 0.65 else "🔴"
        lines = [
            "<b>📈 Evolution report</b>",
            f"{m_emoji} Maturity {maturity_overall:.0%} · sustain {sustainability:.0%}",
            f"Trust {trust_trend} · evo risk {evolution_risk:.0%}",
            f"Autonomy {autonomy_score:.0%} · ops attn {operator_attention:.0%}",
            f"Strategic queue: {strategic_pending} · weak: {weakest_domain}",
        ]
        if long_term_risks:
            lines.append("Risks: " + ", ".join(long_term_risks[:4]))
        lines.append("<i>Long-horizon ops intelligence</i>")
        return "\n".join(lines)
