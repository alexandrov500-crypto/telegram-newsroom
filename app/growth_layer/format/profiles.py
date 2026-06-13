"""Publish format profiles — cb_brief, growth_brief, hybrid."""

from __future__ import annotations

import json
import os
from typing import Any

from app.editorial.cb_brief_format import cb_brief_format_enabled


def growth_layer_enabled() -> bool:
    from app.growth_layer.virality.engine import growth_layer_enabled as _enabled

    return _enabled()


def publish_format_mode() -> str:
    """
    cb_brief | growth_brief | hybrid | subscriber_wire | format_ab
    format_ab = 50/50 subscriber_wire vs cb_brief until forward-rate winner locks.
    """
    raw = os.getenv("NEWSROOM_PUBLISH_FORMAT", "").strip().lower()
    if raw in {"cb_brief", "growth_brief", "hybrid", "subscriber_wire", "format_ab"}:
        return raw
    try:
        from app.editorial.news_channel_beat import news_channel_beat_enabled

        if news_channel_beat_enabled():
            return "format_ab"
    except Exception:
        pass
    if cb_brief_format_enabled():
        return "cb_brief"
    return "cb_brief"


def resolve_publish_format_profile(
    virality_score: int | None = None,
    *,
    draft_id: int | None = None,
    content: str = "",
) -> str:
    """Resolve format for a specific draft (supports format_ab assignment)."""
    mode = publish_format_mode()
    if mode == "format_ab":
        from app.growth.autonomous_robot.format_ab import assign_format_variant

        return assign_format_variant(draft_id=int(draft_id or 0), content=content)
    return resolve_format_profile(virality_score)


def _viral_threshold() -> int:
    try:
        return max(2, min(100, int(os.getenv("VIRALITY_VIRAL_MIN", "71"))))
    except ValueError:
        return 71


def resolve_format_profile(virality_score: int | None) -> str:
    mode = publish_format_mode()
    if mode == "format_ab":
        return "format_ab"
    if mode == "subscriber_wire":
        return "subscriber_wire"
    if mode == "growth_brief":
        return "growth_brief"
    if mode == "hybrid":
        if virality_score is not None and int(virality_score) >= _viral_threshold():
            return "growth_brief"
        return "cb_brief"
    return "cb_brief"


def apply_cb_compose_at_draft_polish() -> bool:
    """Hybrid defers final shape to publish time."""
    if publish_format_mode() == "cb_brief":
        return cb_brief_format_enabled()
    if publish_format_mode() == "growth_brief":
        return False
    return False


def use_cb_brief_at_render(format_profile: str) -> bool:
    return format_profile == "cb_brief"


def use_growth_brief_at_render(format_profile: str) -> bool:
    return format_profile == "growth_brief"


def use_subscriber_wire_at_render(format_profile: str) -> bool:
    return format_profile == "subscriber_wire"


def growth_meta_from_draft_extras(extras_json: str | None) -> dict[str, Any] | None:
    if not extras_json:
        return None
    try:
        data = json.loads(extras_json)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    growth = data.get("growth")
    if not isinstance(growth, dict):
        return None
    return growth


def effective_format_profile(growth_meta: dict[str, Any] | None) -> str:
    if growth_meta and str(growth_meta.get("format_profile") or "").strip():
        return str(growth_meta["format_profile"]).strip()
    score = None
    if growth_meta and growth_meta.get("virality_score") is not None:
        try:
            score = int(growth_meta["virality_score"])
        except (TypeError, ValueError):
            score = None
    return resolve_format_profile(score)
