"""Render bridge — merge product_os into growth_meta for publish."""

from __future__ import annotations

import json
from typing import Any


def merged_growth_meta_with_product_os(extras_json: str | None) -> dict[str, Any] | None:
    from app.editorial.channel_product.render_bridge import merged_growth_meta_from_extras

    base = merged_growth_meta_from_extras(extras_json) or {}
    if not extras_json:
        return base or None
    try:
        data = json.loads(extras_json)
    except (json.JSONDecodeError, TypeError):
        return base or None
    if not isinstance(data, dict):
        return base or None

    peos = data.get("product_os")
    if not isinstance(peos, dict):
        return base or None

    cp = dict(base.get("channel_product") or {})
    cta = peos.get("contextual_cta") if isinstance(peos.get("contextual_cta"), dict) else {}
    if cta.get("line"):
        cp["share_nudge"] = str(cta["line"])
        cp["enable_share_nudge"] = bool(cta.get("enable_share"))
        cp["subscribe_line"] = ""
    cp["product_os"] = peos
    base["channel_product"] = cp

    fmt = peos.get("content_format")
    if fmt:
        base["format_profile"] = "growth_brief" if fmt in {"model", "insight", "digest"} else base.get("format_profile", "cb_brief")
    ref = peos.get("virality_v2") if isinstance(peos.get("virality_v2"), dict) else {}
    if ref.get("total") is not None:
        base["virality_score"] = max(int(base.get("virality_score") or 0), int(float(ref["total"])))

    return base if base else None
