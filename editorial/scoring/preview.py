"""Compact operator-facing HTML for Telegram moderation."""

from __future__ import annotations

from typing import Any

from publisher.formatting import escape_telegram_html
from editorial.scoring.base import level_label


def render_editorial_intelligence_html(intel: dict[str, Any] | None) -> str:
    if not isinstance(intel, dict) or not intel:
        return ""

    q = float(intel.get("quality_score") or 0)
    n = float(intel.get("novelty_score") or 0)
    t = float(intel.get("source_trust_score") or 0)
    cluster = intel.get("cluster_importance_score")
    pri = str(intel.get("publish_priority") or level_label(float(intel.get("publish_priority_score") or 0)).upper())
    reasons = intel.get("reasons") if isinstance(intel.get("reasons"), list) else []

    lines = [
        "",
        "<b>Editorial intelligence</b>",
        f"Quality: <code>{q:.2f}</code> • Novelty: <code>{level_label(n).upper()}</code> • Trust: <code>{level_label(t).upper()}</code>",
    ]
    if cluster is not None:
        lines.append(f"Cluster importance: <code>{float(cluster):.2f}</code> • Priority: <code>{escape_telegram_html(pri)}</code>")
    else:
        lines.append(f"Priority: <code>{escape_telegram_html(pri)}</code>")
    if reasons:
        lines.append("<b>Why selected</b>")
        for r in reasons[:8]:
            lines.append(f"• {escape_telegram_html(str(r))}")
    return "\n".join(lines)
