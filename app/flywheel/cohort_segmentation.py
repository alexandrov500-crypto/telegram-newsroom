"""Cohort segmentation — macro / crypto / geo without per-user tracking."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from db.models import CohortMemory
from db.session import session_scope


COHORTS = ("macro", "crypto", "geopolitics", "finance", "energy", "corporate")


@dataclass(frozen=True)
class CohortProfile:
    cohort: str
    affinity: float
    weight_multiplier: float


def _default_weights() -> dict[str, float]:
    return {c: 0.33 for c in COHORTS}


async def refresh_cohort_memory(runtime_dir: str) -> dict[str, float]:
    """Pull from engagement_feedback vertical weights into cohort_memory table."""
    from app.growth.engagement_feedback import load_engagement_feedback

    fb = load_engagement_feedback(runtime_dir)
    weights = dict(fb.vertical_weights) or _default_weights()
    now = datetime.now(UTC)

    async with session_scope() as session:
        for cohort in COHORTS:
            aff = float(weights.get(cohort, weights.get("general", 0.33)))
            row = (
                await session.execute(select(CohortMemory).where(CohortMemory.cohort == cohort))
            ).scalar_one_or_none()
            if row is None:
                session.add(
                    CohortMemory(
                        cohort=cohort,
                        affinity_score=aff,
                        engagement_sum=aff,
                        sample_count=1,
                        extras_json="{}",
                        updated_at=now,
                    )
                )
            else:
                n = int(row.sample_count or 0)
                row.affinity_score = (float(row.affinity_score) * n + aff) / (n + 1)
                row.sample_count = n + 1
                row.updated_at = now
    return weights


async def load_cohort_weights(runtime_dir: str) -> dict[str, float]:
    async with session_scope() as session:
        rows = list((await session.execute(select(CohortMemory))).scalars().all())
    if not rows:
        from app.growth.engagement_feedback import load_engagement_feedback

        return dict(load_engagement_feedback(runtime_dir).vertical_weights) or _default_weights()
    return {r.cohort: float(r.affinity_score) for r in rows}


def cohort_weight_for_topic(cohort_weights: dict[str, float], topic_bucket: str) -> float:
    c = (topic_bucket or "general").split("_")[0].lower()
    return float(cohort_weights.get(c, cohort_weights.get("general", 0.33)))


def cohort_cadence_multiplier(cohort_weights: dict[str, float], topic_bucket: str) -> float:
    """High-affinity cohorts get slightly higher session cap."""
    w = cohort_weight_for_topic(cohort_weights, topic_bucket)
    return round(0.85 + w * 0.35, 4)
