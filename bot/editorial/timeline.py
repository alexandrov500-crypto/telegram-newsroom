from __future__ import annotations

from datetime import datetime

from bot.storage.story_repository import StoryTimelineEntry


def _format_time(iso_ts: str) -> str:
    try:
        dt = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
        return dt.strftime("%H:%M")
    except ValueError:
        return iso_ts[:5] if len(iso_ts) >= 5 else iso_ts


def compact_timeline_lines(entries: list[StoryTimelineEntry], *, limit: int = 8) -> list[str]:
    """Human-readable milestone lines for digests and admin output."""
    if not entries:
        return []
    tail = entries[-limit:]
    lines: list[str] = []
    for entry in tail:
        time_label = _format_time(entry.created_at)
        headline = entry.headline.strip()
        if len(headline) > 120:
            headline = headline[:117] + "…"
        lines.append(f"{time_label} {headline}")
    return lines


def timeline_context_block(entries: list[StoryTimelineEntry], *, limit: int = 6) -> str:
    lines = compact_timeline_lines(entries, limit=limit)
    if not lines:
        return ""
    return "Prior timeline:\n" + "\n".join(f"- {line}" for line in lines)
