"""Long-lived narrative tracking — cluster lineage and momentum."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select

from db.models import NarrativeTrack
from db.session import session_scope


def _continuation_threshold() -> float:
    try:
        return float(os.getenv("GROWTH_NARRATIVE_CONTINUATION_SIM", "0.55"))
    except ValueError:
        return 0.55


@dataclass(frozen=True)
class NarrativeMatch:
    narrative_id: str
    cluster_key: str
    momentum: float
    is_continuation: bool
    importance: float


def _cluster_key(text: str, category: str = "") -> str:
    from app.editorial.intelligence.trend_memory import infer_narrative_cluster

    return infer_narrative_cluster(text, category=category or "macro")


def _token_set(text: str) -> set[str]:
    return set(re.findall(r"[a-zа-яё0-9]{4,}", (text or "").lower()))


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


async def resolve_narrative(
    *,
    text: str,
    category: str = "general",
    draft_id: int | None = None,
) -> NarrativeMatch:
    """Match or create narrative track for a draft/cluster."""
    cluster = _cluster_key(text, category)
    narrative_id = f"narr:{hashlib.sha256(cluster.encode()).hexdigest()[:12]}"
    tokens = _token_set(text)
    best_sim = 0.0
    parent_id = narrative_id
    is_cont = False

    async with session_scope() as session:
        rows = list(
            (
                await session.execute(
                    select(NarrativeTrack)
                    .where(NarrativeTrack.status == "active")
                    .order_by(NarrativeTrack.updated_at.desc())
                    .limit(40)
                )
            ).scalars()
        )
        for row in rows:
            try:
                prev_tokens = set(json.loads(row.context_tokens_json or "[]"))
            except (json.JSONDecodeError, TypeError):
                prev_tokens = _token_set(row.title or "")
            sim = _jaccard(tokens, prev_tokens)
            if sim > best_sim:
                best_sim = sim
                if sim >= _continuation_threshold():
                    parent_id = row.narrative_id
                    is_cont = True

        momentum = min(1.0, 0.4 + best_sim * 0.5)
        importance = min(1.0, 0.35 + len(tokens) / 40.0)

        existing = (
            await session.execute(select(NarrativeTrack).where(NarrativeTrack.narrative_id == parent_id))
        ).scalar_one_or_none()
        now_ts = time.time()
        if existing is None:
            from datetime import UTC, datetime

            session.add(
                NarrativeTrack(
                    narrative_id=parent_id,
                    cluster_key=cluster,
                    title=(text or "")[:200],
                    vertical=(category or "general")[:32],
                    status="active",
                    momentum_score=momentum,
                    importance_score=importance,
                    publish_count=0,
                    parent_narrative_id="",
                    context_tokens_json=json.dumps(sorted(tokens)[:30]),
                    extras_json=json.dumps({"draft_ids": [draft_id] if draft_id else []}),
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
            )
        else:
            from datetime import UTC, datetime

            existing.momentum_score = max(float(existing.momentum_score), momentum)
            existing.importance_score = max(float(existing.importance_score), importance)
            existing.updated_at = datetime.now(UTC)
            try:
                ex = json.loads(existing.extras_json or "{}")
                dids = list(ex.get("draft_ids") or [])
                if draft_id and draft_id not in dids:
                    dids.append(draft_id)
                ex["draft_ids"] = dids[-20:]
                existing.extras_json = json.dumps(ex)
            except (json.JSONDecodeError, TypeError):
                pass

    return NarrativeMatch(
        narrative_id=parent_id,
        cluster_key=cluster,
        momentum=round(momentum, 4),
        is_continuation=is_cont,
        importance=round(importance, 4),
    )


async def record_narrative_publish(narrative_id: str, *, engagement_score: float = 0.0) -> None:
    async with session_scope() as session:
        row = (
            await session.execute(select(NarrativeTrack).where(NarrativeTrack.narrative_id == narrative_id))
        ).scalar_one_or_none()
        if row is None:
            return
        from datetime import UTC, datetime

        row.publish_count = int(row.publish_count or 0) + 1
        if engagement_score > 0:
            row.momentum_score = min(1.0, float(row.momentum_score) * 0.7 + engagement_score * 0.3)
        row.updated_at = datetime.now(UTC)
