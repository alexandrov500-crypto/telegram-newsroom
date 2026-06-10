"""Policy reporting for weekly growth report."""

from __future__ import annotations

from html import escape
from typing import Any

from app.growth_layer.policy.policy_scoring import PolicyTier


def _label(rec_type: str) -> str:
    return rec_type.replace("_", " ").title()


def recommendation_policy_section(registry: dict[str, Any]) -> list[str]:
    lines = ["", "<b>RECOMMENDATION POLICY</b>"]
    recs = registry.get("recommendations") if isinstance(registry.get("recommendations"), dict) else {}
    if not recs:
        lines.append("Недостаточно данных для policy registry.")
        return lines

    counts = registry.get("tier_counts") or {}
    lines.append(f"Trusted recommendations: <code>{counts.get(PolicyTier.TRUSTED.value, registry.get('trusted_recommendations', 0))}</code>")
    lines.append(f"Experimental: <code>{counts.get(PolicyTier.EXPERIMENTAL.value, registry.get('experimental_recommendations', 0))}</code>")
    lines.append(f"Unverified: <code>{counts.get(PolicyTier.UNVERIFIED.value, registry.get('unverified_recommendations', 0))}</code>")
    lines.append(f"Retired: <code>{counts.get(PolicyTier.RETIRED.value, registry.get('retired_recommendations', 0))}</code>")

    top_trusted = registry.get("top_trusted") or []
    if top_trusted:
        first = top_trusted[0] if isinstance(top_trusted[0], dict) else {}
        rtype = str(first.get("type") or first.get("recommendation_type") or "")
        lines.append("")
        lines.append("Top trusted:")
        lines.append(f"· {_label(rtype)}")
        if first.get("policy_score") is not None:
            lines.append(f"  Policy score: <code>{first.get('policy_score')}</code>")

    top_retired = registry.get("top_retired") or []
    if top_retired:
        first = top_retired[0] if isinstance(top_retired[0], dict) else {}
        rtype = str(first.get("type") or first.get("recommendation_type") or "")
        lines.append("")
        lines.append("Top retired:")
        lines.append(f"· {_label(rtype)}")
        lines.append("  No measurable effect")

    return lines
