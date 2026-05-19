from __future__ import annotations

from datetime import datetime, timezone

from bot.editorial.memory.types import StorylineSnapshot


def _parse_iso(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc)


def _days_ago(iso_ts: str) -> int:
    then = _parse_iso(iso_ts)
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - then
    return max(0, int(delta.total_seconds() // 86400))


def build_context_snippet(
    *,
    storyline: StorylineSnapshot | None,
    follow_up_kind: str,
    headline: str,
) -> str | None:
    """Compact optional continuity line; never a long explainer."""
    if storyline is None or follow_up_kind in ("duplicate", "minor_variation"):
        return None

    days = _days_ago(storyline.last_updated_at)
    topic = storyline.title[:48] if storyline.title else "this story"
    prior = (storyline.latest_headline or "").strip()

    if follow_up_kind == "historical_context":
        if days >= 7:
            return f"This revives coverage of {topic} after {days} days."
        return f"This follows earlier reporting on {topic}."

    if follow_up_kind == "follow_up" and prior:
        if days == 0:
            return f"This updates earlier today: {prior[:72]}."
        if days == 1:
            return f"This follows yesterday's update on {topic}."
        return f"This follows {topic} coverage from {days} days ago."

    if follow_up_kind == "new_development" and storyline.publish_count > 0:
        return f"New angle on {topic}."

    return None
