"""Conversion funnel automation — CTA insertion + event logging."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select

from app.monetization.audience_value import AudienceValueProfile
from db.models import ConversionEvent
from db.session import session_scope


@dataclass(frozen=True)
class FunnelCTA:
    stage: str
    text: str


def _enabled() -> bool:
    return os.getenv("W5_CONVERSION_FUNNEL_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")


def pick_funnel_cta(profile: AudienceValueProfile) -> FunnelCTA | None:
    if not _enabled():
        return None
    link = os.getenv("W5_PREMIUM_CHANNEL_LINK", "").strip()
    if not link:
        return None

    if profile.conversion_probability >= 0.45:
        return FunnelCTA("premium", f"📊 Premium intelligence → {link}")
    if profile.churn_risk >= 0.4:
        return FunnelCTA("retention", f"Ежедневный brief без шума → {link}")
    if profile.ltv_score >= 0.55:
        return FunnelCTA("engagement", f"Deep macro signals → {link}")
    return FunnelCTA("awareness", f"Follow for market context → {link}")


def insert_conversion_cta(content: str, cta: FunnelCTA | None) -> str:
    if not cta or not content:
        return content
    marker = cta.text.strip()
    if marker.lower() in content.lower():
        return content
    max_cta = int(os.getenv("W5_CTA_MAX_PER_POST", "1"))
    if max_cta <= 0:
        return content
    return f"{content.rstrip()}\n\n{marker}"


async def record_conversion_event(
    *,
    event_type: str,
    funnel_stage: str,
    cohort: str,
    draft_id: int | None = None,
    value_score: float = 0.0,
) -> None:
    async with session_scope() as session:
        session.add(
            ConversionEvent(
                event_type=event_type[:32],
                funnel_stage=funnel_stage[:24],
                cohort=cohort[:32],
                draft_id=draft_id,
                value_score=value_score,
                extras_json="{}",
                created_at=datetime.now(UTC),
            )
        )


async def count_conversion_events(event_type: str, *, hours: int = 24) -> int:
    from datetime import timedelta

    cutoff = datetime.now(UTC) - timedelta(hours=hours)
    async with session_scope() as session:
        rows = list(
            (
                await session.execute(
                    select(ConversionEvent).where(
                        ConversionEvent.event_type == event_type,
                        ConversionEvent.created_at >= cutoff,
                    )
                )
            ).scalars()
        )
    return len(rows)
