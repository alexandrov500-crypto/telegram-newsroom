from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any

from bot.editorial.quality.evaluator import EditorialQualityReport, evaluate_pending_item
from bot.editorial.quality.repository import EditorialQualityRepository
from bot.storage.db import default_db_path, init_database

logger = logging.getLogger(__name__)


def _quality_enabled() -> bool:
    raw = os.getenv("EDITORIAL_QUALITY_ENABLED", "true").strip().lower()
    return raw in ("1", "true", "yes", "on")


def get_editorial_quality_repo(db_path: Path | None = None) -> EditorialQualityRepository:
    path = init_database(db_path or default_db_path())
    return EditorialQualityRepository(path)


def record_publish_quality_sync(
    *,
    pending_news_id: int,
    headline: str,
    summary: str,
    link: str,
    tags: list[str],
    source: str | None,
    hook_line: str | None = None,
    db_path: Path | None = None,
) -> EditorialQualityReport | None:
    """Persist editorial quality; never raises."""
    try:
        repo = get_editorial_quality_repo(db_path)
        report = evaluate_pending_item(
            _ItemStub(
                id=pending_news_id,
                link=link,
                tags=tags,
                source=source,
            ),
            headline=headline,
            summary=summary,
            hook_line=hook_line,
            repo=repo,
        )
        repo.record_score(
            pending_news_id=pending_news_id,
            editorial_quality_score=report.editorial_quality_score,
            dimensions=report.dimensions,
            warnings=list(report.warnings),
            fatigue=report.fatigue,
            drift=report.drift,
            headline=headline,
            summary=summary,
            source=source,
            template_key=report.template_key,
            tags=tags,
        )
        _merge_publish_trace(pending_news_id, report, db_path=db_path)
        return report
    except Exception:
        logger.debug("event=editorial_quality_record_failed id=%s", pending_news_id)
        return None


class _ItemStub:
    __slots__ = ("id", "link", "tags", "source")

    def __init__(self, *, id: int, link: str, tags: list[str], source: str | None) -> None:
        self.id = id
        self.link = link
        self.tags = tags
        self.source = source


def _merge_publish_trace(
    pending_news_id: int,
    report: EditorialQualityReport,
    *,
    db_path: Path | None,
) -> None:
    try:
        from bot.live_ops.publish_trace import PublishTraceStore

        store = PublishTraceStore(init_database(db_path or default_db_path()))
        store.merge_fields(
            pending_news_id,
            {
                "editorial_quality_score": report.editorial_quality_score,
                "editorial_quality": {
                    "dimensions": report.dimensions,
                    "warnings": list(report.warnings),
                    "fatigue": report.fatigue,
                    "drift": report.drift,
                    "template_key": report.template_key,
                },
            },
        )
    except Exception:
        logger.debug("event=editorial_quality_trace_merge_failed id=%s", pending_news_id)


def schedule_publish_quality_record(
    *,
    pending_news_id: int,
    headline: str,
    summary: str,
    link: str,
    tags: list[str],
    source: str | None,
    hook_line: str | None = None,
) -> None:
    """Fire-and-forget background record; fail-open."""
    if not _quality_enabled():
        return

    async def _run() -> None:
        await asyncio.to_thread(
            record_publish_quality_sync,
            pending_news_id=pending_news_id,
            headline=headline,
            summary=summary,
            link=link,
            tags=tags,
            source=source,
            hook_line=hook_line,
        )

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_run())
    except RuntimeError:
        record_publish_quality_sync(
            pending_news_id=pending_news_id,
            headline=headline,
            summary=summary,
            link=link,
            tags=tags,
            source=source,
            hook_line=hook_line,
        )


def build_daily_editorial_snapshot(
    repo: EditorialQualityRepository,
    *,
    day: str,
    hours: int = 24,
) -> dict[str, Any]:
    scores = repo.scores_since(hours=hours)
    if not scores:
        return {
            "date": day,
            "count": 0,
            "avg_editorial_quality_score": None,
            "top_recurring_phrases": repo.top_phrases(),
        }
    avg = sum(float(s["editorial_quality_score"]) for s in scores) / len(scores)
    templates: dict[str, int] = {}
    sources: dict[str, int] = {}
    for row in scores:
        tpl = str(row.get("template_key") or "unknown")
        templates[tpl] = templates.get(tpl, 0) + 1
        src = str(row.get("source") or "unknown")
        sources[src] = sources.get(src, 0) + 1
    weakest = sorted(scores, key=lambda r: float(r["editorial_quality_score"]))[:5]
    return {
        "date": day,
        "count": len(scores),
        "avg_editorial_quality_score": round(avg, 3),
        "weakest_headlines": [
            {
                "pending_news_id": w["pending_news_id"],
                "score": w["editorial_quality_score"],
                "headline": (w.get("headline") or "")[:120],
            }
            for w in weakest
        ],
        "top_recurring_phrases": repo.top_phrases(),
        "template_breakdown": templates,
        "source_breakdown": sources,
        "quality_score_trend": [float(s["editorial_quality_score"]) for s in scores[:20]],
    }
