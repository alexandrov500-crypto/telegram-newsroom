"""Financial feedback loop — revenue → editorial weighting."""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from db.models import RevenueEvent, TopicProfitabilityMemory
from db.session import session_scope
from utils.structured_log import log_event

logger = logging.getLogger(__name__)


async def record_revenue_event(
    *,
    draft_id: int | None,
    stream: str,
    surface: str,
    amount_usd: float,
    topic_bucket: str,
    eligibility_score: float,
    extras: dict[str, Any] | None = None,
) -> None:
    async with session_scope() as session:
        session.add(
            RevenueEvent(
                draft_id=draft_id,
                stream=stream[:32],
                surface=surface[:24],
                amount_usd=amount_usd,
                topic_bucket=topic_bucket[:32],
                eligibility_score=eligibility_score,
                extras_json=json.dumps(extras or {}),
                created_at=datetime.now(UTC),
            )
        )


async def refresh_topic_profitability(*, lookback_days: int = 14) -> dict[str, float]:
    """Aggregate revenue_events → topic_profitability_memory."""
    from datetime import timedelta

    cutoff = datetime.now(UTC) - timedelta(days=lookback_days)
    async with session_scope() as session:
        events = list(
            (
                await session.execute(select(RevenueEvent).where(RevenueEvent.created_at >= cutoff))
            ).scalars()
        )
        by_topic: dict[str, list[float]] = {}
        for ev in events:
            by_topic.setdefault(ev.topic_bucket, []).append(float(ev.amount_usd))

        result: dict[str, float] = {}
        for topic, amounts in by_topic.items():
            rev_sum = sum(amounts)
            roi = rev_sum / max(1, len(amounts))
            row = (
                await session.execute(
                    select(TopicProfitabilityMemory).where(TopicProfitabilityMemory.topic_bucket == topic)
                )
            ).scalar_one_or_none()
            now = datetime.now(UTC)
            if row is None:
                session.add(
                    TopicProfitabilityMemory(
                        topic_bucket=topic[:32],
                        revenue_sum=rev_sum,
                        engagement_sum=0.0,
                        roi_score=roi,
                        sample_count=len(amounts),
                        updated_at=now,
                    )
                )
            else:
                n = int(row.sample_count or 0)
                row.revenue_sum = (float(row.revenue_sum) * n + rev_sum) / (n + len(amounts))
                row.roi_score = (float(row.roi_score) * n + roi) / (n + len(amounts))
                row.sample_count = n + len(amounts)
                row.updated_at = now
            result[topic] = round(roi, 4)

    log_event(logger, "monetization.profitability_refreshed", topics=len(result))
    try:
        from pathlib import Path

        cache_path = Path(os.getenv("RUNTIME_STATE_DIR", "var/runtime")) / "topic_roi_cache.json"
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps({"weights": result}), encoding="utf-8")
    except Exception:
        pass
    return result


def load_topic_roi_weights_sync(runtime_dir: str) -> dict[str, float]:
    from pathlib import Path

    try:
        data = json.loads((Path(runtime_dir) / "topic_roi_cache.json").read_text(encoding="utf-8"))
        return {str(k): float(v) for k, v in (data.get("weights") or {}).items()}
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return {}


async def load_topic_roi_weights() -> dict[str, float]:
    async with session_scope() as session:
        rows = list((await session.execute(select(TopicProfitabilityMemory))).scalars())
    if not rows:
        return {}
    return {r.topic_bucket: float(r.roi_score) for r in rows}


def profitability_boost(topic_bucket: str, roi_weights: dict[str, float]) -> float:
    """Multiplier for cadence/ranking — profitable topics get slight boost."""
    key = (topic_bucket or "general").split("_")[0].lower()
    roi = float(roi_weights.get(key, roi_weights.get(topic_bucket, 0.0)))
    if roi <= 0:
        return 1.0
    return round(min(1.15, max(0.88, 0.95 + roi * 0.02)), 4)
