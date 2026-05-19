from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from bot.editorial.memory.analyzer import analyze_editorial_memory
from bot.editorial.memory.contradiction import detect_tone_direction
from bot.editorial.memory.repository import EditorialMemoryRepository
from bot.editorial.memory.types import EditorialMemoryReport
from bot.storage.db import default_db_path, init_database

logger = logging.getLogger(__name__)


def _memory_enabled() -> bool:
    raw = os.getenv("EDITORIAL_MEMORY_ENABLED", "true").strip().lower()
    return raw in ("1", "true", "yes", "on")


def get_editorial_memory_repo(db_path: Path | None = None) -> EditorialMemoryRepository:
    path = init_database(db_path or default_db_path())
    return EditorialMemoryRepository(path)


def record_storyline_event_sync(
    *,
    pending_news_id: int,
    headline: str,
    summary: str,
    tags: list[str],
    source: str | None,
    cluster_id: int | None = None,
    db_path: Path | None = None,
) -> EditorialMemoryReport | None:
    if not _memory_enabled():
        return None
    try:
        repo = get_editorial_memory_repo(db_path)
        report = analyze_editorial_memory(
            headline=headline,
            summary=summary,
            tags=tags,
            source=source,
            repo=repo,
            cluster_id=cluster_id,
        )
        sid = report.storyline_id
        if not sid:
            return report

        new_sid, slug, title, topic_keys, entity_keys = repo.create_storyline_id_for_content(
            headline=headline,
            summary=summary,
            tags=tags,
        )
        is_new = bool(report.metadata.get("is_new_storyline"))
        if not is_new:
            existing = repo.get_storyline(sid)
            if existing:
                slug = existing.slug
                title = existing.title
                topic_keys = list(existing.topic_keys)
                entity_keys = list(existing.entity_keys)
            else:
                sid = new_sid
        else:
            sid = new_sid

        tone = detect_tone_direction(f"{headline} {summary}")

        repo.upsert_storyline(
            storyline_id=sid,
            slug=slug,
            title=title if is_new else (report.storyline_title or title),
            topic_keys=topic_keys,
            entity_keys=entity_keys,
            headline=headline,
            summary=summary,
            source=source,
            tone_direction=tone,
            saturation_score=report.saturation_score,
            cluster_id=cluster_id,
            is_new=is_new,
        )
        repo.record_event(
            storyline_id=sid,
            pending_news_id=pending_news_id,
            event_type="publish",
            follow_up_kind=report.follow_up_kind,
            headline=headline,
            summary=summary,
            source=source,
            tags=tags,
            context_snippet=report.context_snippet,
            contradiction_flags=list(report.contradiction_flags),
            novelty_score=max(0.0, 1.0 - report.match_score),
        )
        _merge_trace_memory(pending_news_id, report, db_path=db_path)
        return report
    except Exception:
        logger.debug("event=editorial_memory_record_failed id=%s", pending_news_id)
        return None


def _merge_trace_memory(
    pending_news_id: int,
    report: EditorialMemoryReport,
    *,
    db_path: Path | None,
) -> None:
    try:
        from bot.live_ops.publish_trace import PublishTraceStore

        store = PublishTraceStore(init_database(db_path or default_db_path()))
        store.merge_fields(
            pending_news_id,
            {
                "storyline_id": report.storyline_id,
                "editorial_memory": {
                    "follow_up_kind": report.follow_up_kind,
                    "context_snippet": report.context_snippet,
                    "warnings": list(report.warnings),
                    "saturation_score": report.saturation_score,
                    "contradiction_flags": list(report.contradiction_flags),
                },
            },
        )
    except Exception:
        pass


def schedule_storyline_record(
    *,
    pending_news_id: int,
    headline: str,
    summary: str,
    tags: list[str],
    source: str | None,
    cluster_id: int | None = None,
) -> None:
    if not _memory_enabled():
        return

    async def _run() -> None:
        await asyncio.to_thread(
            record_storyline_event_sync,
            pending_news_id=pending_news_id,
            headline=headline,
            summary=summary,
            tags=tags,
            source=source,
            cluster_id=cluster_id,
        )

    try:
        asyncio.get_running_loop().create_task(_run())
    except RuntimeError:
        record_storyline_event_sync(
            pending_news_id=pending_news_id,
            headline=headline,
            summary=summary,
            tags=tags,
            source=source,
            cluster_id=cluster_id,
        )


def storyline_html(storyline_id: str, *, db_path: Path | None = None) -> str:
    repo = get_editorial_memory_repo(db_path)
    payload = repo.storyline_timeline_payload(storyline_id)
    if payload is None:
        return f"No storyline <code>{storyline_id}</code>."
    lines = [
        f"<b>Storyline</b> <code>{payload['storyline_id']}</code>",
        f"<b>{payload['title']}</b>",
        f"Topics: {', '.join(payload.get('topic_keys') or [])}",
        f"Publishes: {payload.get('publish_count')} · saturation: {payload.get('saturation_score', 0):.2f}",
        f"Tone: {payload.get('tone_direction') or '—'}",
        f"Sources: {', '.join(payload.get('sources') or []) or '—'}",
        f"First: {str(payload.get('first_seen_at', ''))[:16]} · Last: {str(payload.get('last_updated_at', ''))[:16]}",
        "",
        "<b>Chronology</b>",
    ]
    for ev in (payload.get("events") or [])[:12]:
        flags = ev.get("contradiction_flags") or []
        flag_txt = f" ⚠{','.join(flags)}" if flags else ""
        lines.append(
            f"• [{ev.get('follow_up_kind')}] #{ev.get('pending_news_id')} "
            f"{str(ev.get('created_at', ''))[:16]}\n"
            f"  {(ev.get('headline') or '')[:90]}{flag_txt}",
        )
    return "\n".join(lines)
