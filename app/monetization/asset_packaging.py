"""Media asset packaging — reports, RSS, export bundles."""

from __future__ import annotations

import html
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from db.models import Draft, PublishedPost
from db.session import session_scope


@dataclass(frozen=True)
class MediaBundle:
    bundle_type: str
    title: str
    body: str
    item_count: int


async def fetch_recent_published(*, limit: int = 30) -> list[dict[str, Any]]:
    async with session_scope() as session:
        rows = list(
            (
                await session.execute(
                    select(PublishedPost, Draft)
                    .join(Draft, PublishedPost.draft_id == Draft.id)
                    .order_by(PublishedPost.published_at.desc())
                    .limit(limit)
                )
            ).all()
        )
    items: list[dict[str, Any]] = []
    for pub, draft in rows:
        items.append(
            {
                "draft_id": int(draft.id),
                "telegram_post_id": int(pub.telegram_post_id),
                "published_at": pub.published_at.isoformat() if pub.published_at else "",
                "content": (draft.content or "")[:2000],
                "title": (draft.content or "").split("\n", 1)[0][:160],
            }
        )
    return items


def assemble_weekly_report(items: list[dict[str, Any]]) -> MediaBundle:
    lines = ["# Weekly Intelligence Brief", ""]
    for i, it in enumerate(items[:12], 1):
        lines.append(f"## {i}. {it.get('title', 'Signal')[:120]}")
        lines.append(str(it.get("content", ""))[:400])
        lines.append("")
    body = "\n".join(lines)
    return MediaBundle("weekly_report", "Weekly Intelligence Brief", body, min(12, len(items)))


def build_rss_feed(items: list[dict[str, Any]], *, base_url: str = "") -> str:
    channel_title = os.getenv("W5_RSS_CHANNEL_TITLE", "Newsroom Intelligence Feed").strip()
    channel_link = base_url or os.getenv("W5_RSS_CHANNEL_LINK", "https://t.me/").strip()
    now = datetime.now(UTC).strftime("%a, %d %b %Y %H:%M:%S +0000")
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0"><channel>',
        f"<title>{html.escape(channel_title)}</title>",
        f"<link>{html.escape(channel_link)}</link>",
        f"<description>Structured intelligence feed</description>",
        f"<lastBuildDate>{now}</lastBuildDate>",
    ]
    for it in items:
        title = html.escape(str(it.get("title") or "Signal"))
        desc = html.escape(str(it.get("content") or "")[:800])
        pub = str(it.get("published_at") or now)
        link = f"{channel_link.rstrip('/')}/{it.get('telegram_post_id', '')}"
        parts.extend(
            [
                "<item>",
                f"<title>{title}</title>",
                f"<link>{html.escape(link)}</link>",
                f"<description>{desc}</description>",
                f"<pubDate>{html.escape(pub)}</pubDate>",
                f"<guid isPermaLink=\"false\">draft-{it.get('draft_id')}</guid>",
                "</item>",
            ]
        )
    parts.extend(["</channel></rss>"])
    return "\n".join(parts)


async def build_narrative_report_json(*, limit: int = 20) -> dict[str, Any]:
    from db.models import NarrativeTrack

    async with session_scope() as session:
        tracks = list(
            (
                await session.execute(
                    select(NarrativeTrack).order_by(NarrativeTrack.updated_at.desc()).limit(limit)
                )
            ).scalars()
        )
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "narratives": [
            {
                "narrative_id": t.narrative_id,
                "cluster_key": t.cluster_key,
                "publish_count": int(t.publish_count or 0),
                "momentum": float(t.momentum_score or 0),
                "status": t.status,
            }
            for t in tracks
        ],
    }
