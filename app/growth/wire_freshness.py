"""Wire freshness — prioritize recent source→channel latency for news beat."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from typing import Any


def wire_freshness_enabled() -> bool:
    raw = os.getenv("WIRE_FRESHNESS_PRIORITY", "").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"off", "false", "0", "no"}:
        return False
    try:
        from app.editorial.news_channel_beat import news_channel_beat_enabled

        return news_channel_beat_enabled()
    except Exception:
        return False


def wire_freshness_max_minutes() -> float:
    raw = os.getenv("WIRE_FRESHNESS_MAX_MIN", "25").strip()
    try:
        return max(5.0, min(120.0, float(raw)))
    except ValueError:
        return 25.0


def _parse_created_at(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def draft_age_minutes(draft: Any, *, now: datetime | None = None) -> float:
    anchor = _parse_created_at(getattr(draft, "created_at", None))
    if anchor is None:
        return 9999.0
    ref = now or datetime.now(UTC)
    return max(0.0, (ref - anchor).total_seconds() / 60.0)


def freshness_boost(age_minutes: float, *, max_min: float | None = None) -> float:
    """1.0 for brand-new drafts, decays to ~0.15 past max window."""
    cap = max_min if max_min is not None else wire_freshness_max_minutes()
    if age_minutes <= 3.0:
        return 1.0
    if age_minutes >= cap:
        return 0.12
    # Linear decay inside window
    span = max(1.0, cap - 3.0)
    return round(0.12 + 0.88 * (1.0 - (age_minutes - 3.0) / span), 4)


def is_fastlane_source(channel: str) -> bool:
    key = (channel or "").strip().lower()
    if not key:
        return False
    if not key.startswith("@"):
        key = f"@{key.lstrip('@')}"
    try:
        from app.ops.autonomous_publish import _auto_publish_fastlane_sources

        fl = _auto_publish_fastlane_sources()
        return key in fl or key.lstrip("@") in fl
    except Exception:
        return False


def primary_source_from_json(sources_json: str | None) -> str:
    if not sources_json:
        return ""
    try:
        data = json.loads(sources_json)
    except (json.JSONDecodeError, TypeError):
        return ""
    if not isinstance(data, list) or not data:
        return ""
    row = data[0] if isinstance(data[0], dict) else {}
    return str(row.get("channel") or "").strip()


def wire_priority_score(
    *,
    age_minutes: float,
    sources_json: str | None,
    base_score: float,
) -> float:
    if not wire_freshness_enabled():
        return base_score
    boost = freshness_boost(age_minutes)
    src = primary_source_from_json(sources_json)
    if is_fastlane_source(src):
        boost = min(1.0, boost * 1.18)
    return round(min(1.0, base_score * (0.55 + 0.45 * boost)), 4)
