from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AdaptiveCognitionGovernance:
    """Governance-aware cognition tuning recommendations."""

    _headline_tokens: Counter[str] = field(default_factory=Counter)
    _cluster_sizes: list[int] = field(default_factory=list)
    narrative_instability: float = 0.0

    def observe_story(
        self,
        *,
        headline: str,
        cluster_size: int = 1,
        trust: float = 0.85,
        engagement: float = 0.5,
    ) -> dict[str, Any]:
        tokens = headline.lower().split()[:4]
        if tokens:
            self._headline_tokens[" ".join(tokens)] += 1
        self._cluster_sizes.append(cluster_size)
        if len(self._cluster_sizes) > 100:
            self._cluster_sizes = self._cluster_sizes[-100:]

        repetitiveness = max(self._headline_tokens.values()) if self._headline_tokens else 0
        over_cluster = sum(1 for s in self._cluster_sizes if s > 8) / max(len(self._cluster_sizes), 1)
        fragmentation = sum(1 for s in self._cluster_sizes if s == 1) / max(len(self._cluster_sizes), 1)

        aggressiveness = max(0.3, min(1.0, trust * engagement))
        summary_depth = "deep" if engagement > 0.65 else "standard" if engagement > 0.4 else "brief"
        self.narrative_instability = min(1.0, repetitiveness / 10.0 + over_cluster)

        return {
            "cognition_aggressiveness": round(aggressiveness, 2),
            "summary_depth": summary_depth,
            "repetitive_coverage_risk": repetitiveness > 5,
            "over_clustering": over_cluster > 0.3,
            "fragmentation": fragmentation > 0.5,
        }

    def narrative_health_text(self) -> str:
        rep = max(self._headline_tokens.values()) if self._headline_tokens else 0
        emoji = "🟢" if self.narrative_instability < 0.3 else "🟡" if self.narrative_instability < 0.6 else "🔴"
        return (
            f"<b>{emoji} Narrative health</b>\n"
            f"Instability {self.narrative_instability:.2f}\n"
            f"Top headline repeat: {rep}×\n"
            f"{'⚠️ Suppress repetitive coverage' if rep > 5 else 'Coverage diverse'}"
        )

    def editorial_diversity_text(self) -> str:
        if not self._cluster_sizes:
            return "Insufficient cluster samples."
        frag = sum(1 for s in self._cluster_sizes if s == 1) / len(self._cluster_sizes)
        over = sum(1 for s in self._cluster_sizes if s > 8) / len(self._cluster_sizes)
        return (
            f"<b>Editorial diversity</b>\n"
            f"Fragmentation {frag:.0%} · mega-clusters {over:.0%}\n"
            f"Blind spot: {'many singleton stories' if frag > 0.5 else 'balanced'}"
        )
