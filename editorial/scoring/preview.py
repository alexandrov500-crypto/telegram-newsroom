"""Compact operator-facing HTML for Telegram moderation."""

from __future__ import annotations

from typing import Any

from editorial.scoring.base import level_label
from publisher.formatting import escape_telegram_html
from publisher.operator_ui_ru import tr_level_label, tr_publish_priority_label, tr_scoring_reason


def render_editorial_intelligence_html(intel: dict[str, Any] | None) -> str:
    if not isinstance(intel, dict) or not intel:
        return ""

    q = float(intel.get("quality_score") or 0)
    n = float(intel.get("novelty_score") or 0)
    t = float(intel.get("source_trust_score") or 0)
    cluster = intel.get("cluster_importance_score")
    pri_raw = str(intel.get("publish_priority") or level_label(float(intel.get("publish_priority_score") or 0))).upper()
    pri = tr_publish_priority_label(pri_raw)
    reasons = intel.get("reasons") if isinstance(intel.get("reasons"), list) else []
    version = str(intel.get("scoring_version") or "")

    lines = [
        "",
        "<b>Редакционная оценка</b>",
        f"Качество: <code>{q:.2f}</code> • Новизна: <code>{tr_level_label(level_label(n))}</code> • "
        f"Доверие: <code>{tr_level_label(level_label(t))}</code>",
    ]
    if cluster is not None:
        lines.append(
            f"Важность кластера: <code>{float(cluster):.2f}</code> • Приоритет: <code>{escape_telegram_html(pri)}</code>"
        )
    else:
        lines.append(f"Приоритет: <code>{escape_telegram_html(pri)}</code>")
    if version:
        lines.append(f"<i>версия скоринга</i> <code>{escape_telegram_html(version)}</code>")
    if reasons:
        lines.append("<b>Почему выбрано</b>")
        for r in reasons[:8]:
            lines.append(f"• {escape_telegram_html(tr_scoring_reason(str(r)))}")
    return "\n".join(lines)
