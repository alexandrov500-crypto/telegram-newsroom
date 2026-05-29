"""B2B feed normalization — API product data layer."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.monetization.asset_packaging import build_narrative_report_json, fetch_recent_published
from db.models import PostPerformance, SourceRegistryEntry
from db.session import session_scope


@dataclass(frozen=True)
class RateLimitVerdict:
    allowed: bool
    remaining: int
    reason: str


def _rate_state_path() -> Path:
    base = os.getenv("RUNTIME_STATE_DIR", "var/runtime")
    return Path(base) / "b2b_api_rate_limit.json"


def check_rate_limit(api_key: str, *, limit_per_hour: int | None = None) -> RateLimitVerdict:
    lim = limit_per_hour or int(os.getenv("W5_B2B_API_RATE_LIMIT_HOUR", "120"))
    hour_bucket = datetime.now(UTC).strftime("%Y%m%d%H")
    p = _rate_state_path()
    try:
        state = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        state = {}

    key = f"{api_key[:8]}:{hour_bucket}"
    used = int((state.get(key) or {}).get("count") or 0)
    if used >= lim:
        return RateLimitVerdict(False, 0, "rate_limited")

    state[key] = {"count": used + 1, "ts": time.time()}
    for k in list(state.keys())[:-200]:
        if k != key:
            state.pop(k, None)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state), encoding="utf-8")
    return RateLimitVerdict(True, lim - used - 1, "ok")


def validate_api_key(headers: dict[str, str], query: dict[str, list[str]]) -> str | None:
    expected = os.getenv("W5_B2B_API_KEY", "").strip()
    if not expected:
        return None
    token = headers.get("x-api-key") or headers.get("authorization", "").replace("Bearer ", "").strip()
    if not token and query.get("api_key"):
        token = query["api_key"][0]
    return token if token == expected else ""


async def build_news_feed(*, limit: int = 50) -> dict[str, Any]:
    items = await fetch_recent_published(limit=limit)
    return {
        "schema": "newsroom.feed.v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "count": len(items),
        "items": [
            {
                "id": f"draft:{it['draft_id']}",
                "title": it.get("title"),
                "summary": (it.get("content") or "")[:500],
                "published_at": it.get("published_at"),
                "telegram_post_id": it.get("telegram_post_id"),
            }
            for it in items
        ],
    }


async def build_signals_feed(*, limit: int = 40) -> dict[str, Any]:
    async with session_scope() as session:
        rows = list(
            (
                await session.execute(
                    select(PostPerformance)
                    .where(PostPerformance.snapshot_label == "t6h")
                    .order_by(PostPerformance.engagement_score.desc())
                    .limit(limit)
                )
            ).scalars()
        )
    return {
        "schema": "newsroom.signals.v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "signals": [
            {
                "draft_id": r.draft_id,
                "engagement_score": float(r.engagement_score),
                "virality_score": float(r.virality_score),
                "topic_bucket": r.topic_bucket,
                "impact_proxy": round(float(r.engagement_score) * 0.6 + float(r.virality_score) * 0.4, 4),
            }
            for r in rows
        ],
    }


async def build_source_reliability_index() -> dict[str, Any]:
    async with session_scope() as session:
        rows = list((await session.execute(select(SourceRegistryEntry))).scalars())
    return {
        "schema": "newsroom.sources.v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "sources": [
            {
                "channel": r.handle,
                "tier": r.tier,
                "trust_score": float(r.trust_score or 0),
                "reliability_index": round(
                    float(r.trust_score or 0.5) * 0.7 + (1.0 if r.tier == "T0" else 0.6) * 0.3,
                    4,
                ),
            }
            for r in rows
        ],
    }


async def build_narratives_api() -> dict[str, Any]:
    data = await build_narrative_report_json(limit=30)
    data["schema"] = "newsroom.narratives.v1"
    return data
