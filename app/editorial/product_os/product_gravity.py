"""Product Gravity (PG) — editorial value for cognitive substitution."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.editorial.product_os.config import pg_digest_threshold, pg_flagship_threshold, pg_publish_threshold


class PGAction(str, Enum):
    FLAGSHIP = "flagship_priority_push"
    PUBLISH = "publish"
    DIGEST = "digest_merge"
    REJECT = "reject"


@dataclass(frozen=True)
class ProductGravityBreakdown:
    informational_value: float
    cross_domain_relevance: float
    substitution_potential: float
    clarity: float
    novelty: float
    reference_potential: float
    total: float
    action: PGAction
    skip_cadence_cap: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "informational_value": round(self.informational_value, 2),
            "cross_domain_relevance": round(self.cross_domain_relevance, 2),
            "substitution_potential": round(self.substitution_potential, 2),
            "clarity": round(self.clarity, 2),
            "novelty": round(self.novelty, 2),
            "reference_potential": round(self.reference_potential, 2),
            "total": round(self.total, 2),
            "action": self.action.value,
            "skip_cadence_cap": self.skip_cadence_cap,
        }


def compute_product_gravity(
    *,
    quality_score: float,
    cross_domain_density: float,
    substitution_score: float,
    clarity: float,
    reference_forward_total: float,
    novelty_hint: float = 0.0,
    publishing_mode: str = "core",
) -> ProductGravityBreakdown:
    info_val = min(100.0, quality_score * 1.15)
    cross = min(100.0, cross_domain_density * 100.0)
    subst = min(100.0, substitution_score)
    clar = min(100.0, clarity)
    novelty = min(100.0, 40.0 + novelty_hint * 60.0)
    ref_pot = min(100.0, reference_forward_total)

    total = (
        0.25 * info_val
        + 0.20 * cross
        + 0.20 * subst
        + 0.15 * clar
        + 0.10 * novelty
        + 0.10 * ref_pot
    )
    total = max(0.0, min(100.0, total))

    flagship_thr = float(pg_flagship_threshold())
    pub_thr = float(pg_publish_threshold())
    dig_thr = float(pg_digest_threshold())

    skip_cap = False
    if total >= flagship_thr:
        action = PGAction.FLAGSHIP
        skip_cap = True
    elif total >= pub_thr:
        action = PGAction.PUBLISH
    elif total >= dig_thr:
        action = PGAction.DIGEST
    elif publishing_mode in {"elastic_fill", "editorial_synthesis"}:
        action = PGAction.DIGEST
    else:
        action = PGAction.REJECT

    return ProductGravityBreakdown(
        informational_value=info_val,
        cross_domain_relevance=cross,
        substitution_potential=subst,
        clarity=clar,
        novelty=novelty,
        reference_potential=ref_pot,
        total=total,
        action=action,
        skip_cadence_cap=skip_cap,
    )
