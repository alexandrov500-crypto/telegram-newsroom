"""Cross-Channel Replacement Score — can this post replace 5–10 feeds?"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.editorial.audience_unification.config import crs_flagship_threshold


@dataclass(frozen=True)
class CRSBreakdown:
    breadth_of_relevance: float
    clarity: float
    informational_density: float
    decision_value: float
    novelty: float
    cross_domain_links: float
    total: float
    tier: str
    action: str
    flagship: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "breadth_of_relevance": round(self.breadth_of_relevance, 2),
            "clarity": round(self.clarity, 2),
            "informational_density": round(self.informational_density, 2),
            "decision_value": round(self.decision_value, 2),
            "novelty": round(self.novelty, 2),
            "cross_domain_links": round(self.cross_domain_links, 2),
            "total": round(self.total, 2),
            "tier": self.tier,
            "action": self.action,
            "flagship": self.flagship,
        }


def _clamp(v: float) -> float:
    return max(0.0, min(100.0, v))


def compute_crs(
    text: str,
    *,
    cross_interest_breadth: int = 0,
    reader_clarity: float = 50.0,
    quality_score: float = 0.0,
    has_implication: bool = False,
    cluster_size: int = 1,
) -> CRSBreakdown:
    t = text or ""
    words = len(t.split())

    breadth = _clamp(35.0 + cross_interest_breadth * 14.0)
    clarity = _clamp(reader_clarity)
    density = _clamp(min(100.0, words * 1.8 + (10 if cluster_size > 1 else 0)))
    decision = _clamp(quality_score * 1.2 + (20 if has_implication else 0))
    novelty = _clamp(45.0 + (15 if re.search(r"(breaking|срочно|впервые|unexpected)", t, re.I) else 0))
    cross_links = _clamp(cross_interest_breadth * 18.0 + (12 if cluster_size >= 2 else 0))

    total = (breadth + clarity + density + decision + novelty + cross_links) / 6.0
    total = _clamp(total)

    flagship = total >= crs_flagship_threshold()
    if total >= 85:
        tier, action = "flagship", "must_read"
    elif total >= 70:
        tier, action = "publish", "publish"
    elif total >= 50:
        tier, action = "digest", "digest_merge"
    else:
        tier, action = "reject", "reject"

    return CRSBreakdown(
        breadth_of_relevance=breadth,
        clarity=clarity,
        informational_density=density,
        decision_value=decision,
        novelty=novelty,
        cross_domain_links=cross_links,
        total=total,
        tier=tier,
        action=action,
        flagship=flagship,
    )
