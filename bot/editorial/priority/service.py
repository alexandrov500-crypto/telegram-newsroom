from __future__ import annotations

import asyncio
import html
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bot.editorial.memory.service import get_editorial_memory_repo
from bot.editorial.priority.drift import analyze_priority_drift
from bot.editorial.priority.ranker import RankedQueueItem, rank_pending_items
from bot.editorial.priority.repository import EditorialPriorityRepository
from bot.editorial.priority.scoring import EditorialPriorityResult
from bot.storage.db import default_db_path, init_database
from bot.storage.editorial_repository import EditorialRepository, PendingNewsItem
from bot.storage.source_repository import SourceRepository

logger = logging.getLogger(__name__)


def _enabled() -> bool:
    raw = os.getenv("EDITORIAL_PRIORITY_ENABLED", "true").strip().lower()
    return raw in ("1", "true", "yes", "on")


def get_priority_repo(db_path: Path | None = None) -> EditorialPriorityRepository:
    return EditorialPriorityRepository(init_database(db_path or default_db_path()))


def build_ranked_queue(
    *,
    limit: int = 15,
    db_path: Path | None = None,
) -> tuple[list[RankedQueueItem], dict[str, Any]]:
    path = init_database(db_path or default_db_path())
    editorial = EditorialRepository(path)
    memory_repo = get_editorial_memory_repo(path)
    sources = SourceRepository(path)
    items = editorial.get_pending_news(limit=max(limit, 30))
    ranked = rank_pending_items(items, memory_repo=memory_repo, sources=sources)
    prio_repo = EditorialPriorityRepository(path)
    drift = analyze_priority_drift(prio_repo.recent_scores(hours=72))
    meta = {"drift": drift, "queue_size": len(ranked)}
    return ranked[:limit], meta


def priority_queue_html(
    *,
    limit: int = 12,
    db_path: Path | None = None,
) -> str:
    if not _enabled():
        return "<b>Priority queue</b> disabled (EDITORIAL_PRIORITY_ENABLED)."
    ranked, meta = build_ranked_queue(limit=limit, db_path=db_path)
    drift = meta.get("drift") or {}
    lines = [
        "<b>Editorial priority queue</b>",
        f"Drift: <code>{html.escape(str(drift.get('drift_alert', 'stable')))}</code> · "
        f"avg pri {drift.get('avg_priority', 0):.2f} · "
        f"noise ratio {drift.get('noise_ratio', 0):.2f}",
        "",
    ]
    if not ranked:
        lines.append("No pending items in queue.")
        return "\n".join(lines)

    for idx, row in enumerate(ranked, start=1):
        p = row.priority
        warn = f" ⚠{len(p.warnings)}" if p.warnings else ""
        why = "; ".join(p.why_ranked[:2]) if p.why_ranked else "—"
        lines.append(
            f"{idx}. <b>#{row.item.id}</b> "
            f"<code>{p.editorial_priority_score:.2f}</code> "
            f"[{html.escape(p.urgency_class)}]{warn}\n"
            f"   {html.escape(row.headline[:85])}\n"
            f"   <i>{html.escape(why)}</i>",
        )
        if p.warnings:
            for w in p.warnings[:2]:
                lines.append(f"   ⚠ {html.escape(w)}")
        if row.storyline_id:
            lines.append(
                f"   storyline <code>{html.escape(row.storyline_id)}</code> · "
                f"{html.escape(row.memory_follow_up or '—')}",
            )
    return "\n".join(lines)


def priority_queue_payload(*, limit: int = 20, db_path: Path | None = None) -> dict[str, Any]:
    ranked, meta = build_ranked_queue(limit=limit, db_path=db_path)
    return {
        "status": "ok",
        "count": len(ranked),
        "drift": meta.get("drift"),
        "items": [
            {
                "rank": i + 1,
                "pending_news_id": r.item.id,
                "headline": r.headline,
                "editorial_priority_score": r.priority.editorial_priority_score,
                "urgency_class": r.priority.urgency_class,
                "factors": r.priority.factors.to_dict(),
                "warnings": list(r.priority.warnings),
                "why_ranked": list(r.priority.why_ranked),
                "storyline_id": r.storyline_id,
                "follow_up_kind": r.memory_follow_up,
            }
            for i, r in enumerate(ranked)
        ],
    }


def evaluate_item_priority(
    item: PendingNewsItem,
    *,
    db_path: Path | None = None,
) -> EditorialPriorityResult:
    path = init_database(db_path or default_db_path())
    memory_repo = get_editorial_memory_repo(path)
    sources = SourceRepository(path)
    ranked = rank_pending_items([item], memory_repo=memory_repo, sources=sources)
    return ranked[0].priority


def schedule_priority_record(
    *,
    pending_news_id: int,
    result: EditorialPriorityResult,
    db_path: Path | None = None,
) -> None:
    if not _enabled():
        return

    async def _run() -> None:
        await asyncio.to_thread(_record_sync, pending_news_id=pending_news_id, result=result, db_path=db_path)

    try:
        asyncio.get_running_loop().create_task(_run())
    except RuntimeError:
        _record_sync(pending_news_id=pending_news_id, result=result, db_path=db_path)


def _record_sync(
    *,
    pending_news_id: int,
    result: EditorialPriorityResult,
    db_path: Path | None,
) -> None:
    try:
        repo = get_priority_repo(db_path)
        repo.record(
            pending_news_id=pending_news_id,
            editorial_priority_score=result.editorial_priority_score,
            urgency_class=result.urgency_class,
            factors=result.factors.to_dict(),
            warnings=list(result.warnings),
            momentum=dict(result.momentum),
            balance=dict(result.balance),
        )
        from bot.live_ops.publish_trace import PublishTraceStore

        store = PublishTraceStore(init_database(db_path or default_db_path()))
        store.merge_fields(
            pending_news_id,
            {
                "editorial_priority_score": result.editorial_priority_score,
                "urgency_class": result.urgency_class,
                "editorial_priority": {
                    "factors": result.factors.to_dict(),
                    "warnings": list(result.warnings),
                    "why_ranked": list(result.why_ranked),
                },
            },
        )
    except Exception:
        logger.debug("event=priority_record_failed id=%s", pending_news_id)


def build_daily_priority_snapshot(db_path: Path | None = None) -> dict[str, Any]:
    repo = get_priority_repo(db_path)
    recent = repo.recent_scores(hours=24, limit=100)
    drift = analyze_priority_drift(recent)
    day = datetime.now(timezone.utc).date().isoformat()
    snap = {"date": day, "count": len(recent), **drift}
    repo.save_daily(day, snap)
    return snap
