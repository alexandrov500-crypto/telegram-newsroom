"""Audience Replacement Principle — post must replace ≥3 external channels."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.editorial.unified_operating_system.config import ueos_min_channel_replacement

_MULTI_DOMAIN = re.compile(
    r"(macro|market|рынок|ai|openai|crypto|геополит|sanction|fed|tech|бизнес|global|глобал)",
    re.I,
)
_SYNTHESIS = re.compile(r"(сводк|единая\s+картин|несколько\s+источник|merge|world\s+signal|сигнал)", re.I)
_DECISION = re.compile(r"(решени|decision|инвестор|стратег|риск|ставк|policy|политик)", re.I)
_SYSTEMIC = re.compile(r"(систем|implication|почему\s+важ|глобальн|контекст|mental\s+model|ментальн)", re.I)


@dataclass(frozen=True)
class ReplacementScore:
    replaces_external_channels: bool
    estimated_channels_replaced: int
    multi_domain: bool
    synthesis: bool
    decision_signal: bool
    systemic_implication: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "replaces_external_channels": self.replaces_external_channels,
            "estimated_channels_replaced": self.estimated_channels_replaced,
            "multi_domain": self.multi_domain,
            "synthesis": self.synthesis,
            "decision_signal": self.decision_signal,
            "systemic_implication": self.systemic_implication,
            "reason": self.reason,
        }


def evaluate_channel_replacement(
    text: str,
    *,
    cross_topic_breadth: int = 0,
    cluster_size: int = 1,
    crs_total: float = 0.0,
) -> ReplacementScore:
    t = text or ""
    domains = len(set(_MULTI_DOMAIN.findall(t)))
    multi = domains >= 2 or cross_topic_breadth >= 2
    synth = bool(_SYNTHESIS.search(t)) or cluster_size >= 2
    decision = bool(_DECISION.search(t))
    systemic = bool(_SYSTEMIC.search(t))

    estimated = 0
    if multi:
        estimated += max(1, min(domains, 3))
    if synth:
        estimated += 2
    if decision:
        estimated += 1
    if systemic:
        estimated += 1
    if crs_total >= 70:
        estimated += 1

    min_rep = ueos_min_channel_replacement()
    replaces = estimated >= min_rep or (multi and systemic and decision)

    reason = "replacement_ok" if replaces else "insufficient_cross_source_value"
    if not multi and not synth:
        reason = "single_domain_no_synthesis"

    return ReplacementScore(
        replaces_external_channels=replaces,
        estimated_channels_replaced=min(estimated, 12),
        multi_domain=multi,
        synthesis=synth,
        decision_signal=decision,
        systemic_implication=systemic,
        reason=reason,
    )
