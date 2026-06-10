"""Render bridge — merge channel_product into growth_meta for publish formatter."""

from __future__ import annotations

import json
from typing import Any


def channel_product_from_extras(extras_json: str | None) -> dict[str, Any] | None:
    if not extras_json:
        return None
    try:
        data = json.loads(extras_json)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    cp = data.get("channel_product")
    return cp if isinstance(cp, dict) else None


def merged_growth_meta_from_extras(extras_json: str | None) -> dict[str, Any] | None:
    """Merge growth + channel_product for public_post_formatter."""
    if not extras_json:
        return None
    try:
        data = json.loads(extras_json)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        return None

    growth: dict[str, Any] = {}
    g = data.get("growth")
    if isinstance(g, dict):
        growth.update(g)

    cp = data.get("channel_product")
    if isinstance(cp, dict):
        if cp.get("format_profile"):
            growth["format_profile"] = cp["format_profile"]
        if cp.get("viral_tier"):
            growth["virality_tier"] = cp["viral_tier"]
        if cp.get("reference_forward_score") is not None:
            growth["virality_score"] = max(
                int(growth.get("virality_score") or 0),
                int(float(cp["reference_forward_score"])),
            )
        growth["channel_product"] = cp

    return growth if growth else None
