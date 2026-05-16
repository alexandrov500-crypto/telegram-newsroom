from __future__ import annotations

import json
import logging
from typing import Any

from app.config import Settings
from utils.structured_log import log_event

logger = logging.getLogger(__name__)


def _parse_routing_rules(raw: str) -> dict[str, Any]:
    if not (raw or "").strip():
        return {}
    try:
        out = json.loads(raw)
        return out if isinstance(out, dict) else {}
    except (json.JSONDecodeError, TypeError):
        log_event(logger, "routing.rules_json_invalid")
        return {}


def route_draft_to_channel(
    settings: Settings,
    *,
    tags: list[str] | None = None,
    category: str | None = None,
    severity: str | None = None,
    sources: list[dict[str, Any]] | None = None,
    manual_channel_id: int | None = None,
) -> int:
    """
    Resolve target Telegram channel id for a draft (single-node mapping).
    Precedence: manual override → tag match → category → severity → default target_channel_id.
    """
    if manual_channel_id is not None:
        return int(manual_channel_id)

    rules = _parse_routing_rules(settings.channel_routing_rules_json)
    by_tag = rules.get("by_tag") or {}
    by_category = rules.get("by_category") or {}
    by_severity = rules.get("by_severity") or {}
    by_source = rules.get("by_source_prefix") or {}

    for t in tags or []:
        key = str(t).lstrip("#").strip().lower()
        if key and key in by_tag:
            return int(by_tag[key])

    if category:
        ck = str(category).strip().lower()
        if ck in by_category:
            return int(by_category[ck])

    if severity:
        sk = str(severity).strip().lower()
        if sk in by_severity:
            return int(by_severity[sk])

    for src in sources or []:
        ch = str(src.get("channel", "")).strip().lower()
        for prefix, cid in by_source.items():
            if ch.startswith(str(prefix).lower()):
                return int(cid)

    return int(settings.target_channel_id)
