"""Digest intelligence — retention engine for public channel."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from db.models import GrowthDigestRun, PostPerformance
from db.session import session_scope


@dataclass(frozen=True)
class DigestCandidate:
    draft_id: int | None
    topic_bucket: str
    engagement_score: float
    virality_score: float
    headline: str
    narrative_id: str


def _digest_enabled() -> bool:
    return os.getenv("GROWTH_DIGEST_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")


def _rank_score(c: DigestCandidate) -> float:
    return 0.5 * c.engagement_score + 0.35 * c.virality_score + 0.15 * min(1.0, len(c.headline) / 120.0)


async def fetch_digest_candidates(*, since_hours: int = 12, limit: int = 20) -> list[DigestCandidate]:
    cutoff = datetime.now(UTC) - timedelta(hours=since_hours)
    out: list[DigestCandidate] = []
    async with session_scope() as session:
        q = (
            select(PostPerformance)
            .where(
                PostPerformance.snapshot_at >= cutoff,
                PostPerformance.snapshot_label.in_(("t6h", "t24h")),
                PostPerformance.engagement_score > 0,
            )
            .order_by(PostPerformance.engagement_score.desc())
            .limit(limit * 2)
        )
        rows = list((await session.execute(q)).scalars().all())
    seen_topics: set[str] = set()
    for r in rows:
        tb = (r.topic_bucket or "general").lower()
        if tb in seen_topics and len(out) >= 3:
            continue
        seen_topics.add(tb)
        out.append(
            DigestCandidate(
                draft_id=r.draft_id,
                topic_bucket=tb,
                engagement_score=float(r.engagement_score or 0),
                virality_score=float(r.virality_score or 0),
                headline=(r.primary_source or tb)[:120],
                narrative_id="",
            )
        )
        if len(out) >= limit:
            break
    return out


def assemble_digest_html(
    digest_type: str,
    candidates: list[DigestCandidate],
    *,
    narrative_lines: list[str] | None = None,
) -> str:
    """Template structure for morning/evening/weekly digests."""
    ranked = sorted(candidates, key=_rank_score, reverse=True)
    if digest_type == "morning_briefing":
        title = "☀️ Утренний брифинг"
        intro = "Главное за ночь и открытие сессии:"
    elif digest_type == "evening_recap":
        title = "🌆 Итоги дня"
        intro = "Ключевые события, которые двигали рынки:"
    else:
        title = "📊 5 событий недели"
        intro = "Недельный обзор — что имело значение:"

    lines = [f"<b>{title}</b>", "", intro, ""]
    for i, c in enumerate(ranked[:5 if digest_type != "weekly_key_events" else 5], 1):
        lines.append(f"{i}. <b>{c.topic_bucket.upper()}</b> — score {c.engagement_score:.2f}")
    if narrative_lines:
        lines.extend(["", "<b>Контекст:</b>"] + narrative_lines[:3])
    lines.append("")
    lines.append("<i>Digest · retention engine</i>")
    return "\n".join(lines)


def diversity_score(candidates: list[DigestCandidate]) -> float:
    if not candidates:
        return 0.0
    topics = {c.topic_bucket for c in candidates}
    return round(min(1.0, len(topics) / max(1, len(candidates))), 4)


async def run_digest_generation(
    *,
    digest_type: str,
    since_hours: int = 12,
) -> dict[str, Any]:
    if not _digest_enabled():
        return {"skipped": True, "reason": "disabled"}
    candidates = await fetch_digest_candidates(since_hours=since_hours)
    if len(candidates) < 2:
        return {"skipped": True, "reason": "insufficient_candidates", "count": len(candidates)}

    html = assemble_digest_html(digest_type, candidates)
    div = diversity_score(candidates)
    from datetime import UTC, datetime

    async with session_scope() as session:
        row = GrowthDigestRun(
            digest_type=digest_type,
            status="generated",
            content=html,
            item_count=len(candidates),
            diversity_score=div,
            extras_json=json.dumps({"candidate_ids": [c.draft_id for c in candidates[:10]]}),
            created_at=datetime.now(UTC),
        )
        session.add(row)
        await session.flush()
        digest_id = int(row.id)

    return {"digest_id": digest_id, "item_count": len(candidates), "diversity": div, "html_len": len(html)}
