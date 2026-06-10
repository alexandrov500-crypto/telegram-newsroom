"""Channel Substitution Engine — post vs 10–20 external Telegram channels."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.editorial.product_os.config import cse_min_channels

_DOMAIN = re.compile(
    r"(macro|market|рынок|ai|openai|crypto|btc|геополит|sanction|fed|tech|бизнес|global|local|город)",
    re.I,
)
_DECISION = re.compile(r"(decision|решени|инвестор|риск|ставк|policy|стратег)", re.I)
_MENTAL = re.compile(r"(ментальн|mental\s+model|понимать|framework|модель|вывод)", re.I)
_SYNTHESIS = re.compile(r"(сводк|digest|единая|несколько\s+источник|compress|world\s+signal)", re.I)
_WHY = re.compile(r"(почему\s+важ|why\s+it\s+matters|важн|значит|implication)", re.I)


@dataclass(frozen=True)
class CSEResult:
    channels_replaced_estimate: int
    cross_domain_density: float
    valid: bool
    reason: str
    multi_domain: bool
    decision_insight: bool
    mental_model: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "channels_replaced_estimate": self.channels_replaced_estimate,
            "cross_domain_density": round(self.cross_domain_density, 3),
            "valid": self.valid,
            "reason": self.reason,
            "multi_domain": self.multi_domain,
            "decision_insight": self.decision_insight,
            "mental_model": self.mental_model,
            "substitution_score": round(min(100.0, self.channels_replaced_estimate * 12.0 + self.cross_domain_density * 40), 2),
        }


def evaluate_channel_substitution(
    text: str,
    *,
    cluster_size: int = 1,
    cross_topic_breadth: int = 0,
) -> CSEResult:
    t = text or ""
    domains = len(set(_DOMAIN.findall(t)))
    cross_density = min(1.0, (domains + cross_topic_breadth) / 6.0)
    multi = domains >= 2 or cross_topic_breadth >= 2
    decision = bool(_DECISION.search(t))
    mental = bool(_MENTAL.search(t))
    synth = bool(_SYNTHESIS.search(t)) or cluster_size >= 2
    why = bool(_WHY.search(t))

    est = 0
    if multi:
        est += min(4, domains)
    if synth:
        est += 3
    if decision:
        est += 2
    if mental:
        est += 2
    if why:
        est += 1
    if cluster_size >= 3:
        est += 2

    min_ch = cse_min_channels()
    valid = (
        est >= min_ch
        or (multi and decision)
        or (mental and why)
        or synth
    )
    reason = "substitution_ok" if valid else "insufficient_channel_replacement"
    if not multi and not synth:
        reason = "single_domain_weak"

    return CSEResult(
        channels_replaced_estimate=min(est, 15),
        cross_domain_density=cross_density,
        valid=valid,
        reason=reason,
        multi_domain=multi,
        decision_insight=decision,
        mental_model=mental,
    )
