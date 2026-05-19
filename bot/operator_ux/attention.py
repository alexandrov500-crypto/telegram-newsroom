from __future__ import annotations

import html
from typing import Any

from bot.operator_ux.compress import compress_editorial_item, compress_priority_rationale
from bot.operator_ux.incidents import group_incidents
from bot.operator_ux.severity import AttentionSeverity, classify_editorial_warning


def build_attention_queue_html(ctx: dict[str, Any]) -> str:
    """Focus queue: critical decisions only."""
    lines = ["<b>Attention queue</b>", "<i>Operator triage — highest signal first</i>", ""]

    pulse = ctx.get("pulse") or {}
    drift = ctx.get("priority_drift") or {}
    incidents = group_incidents(
        live_incidents=ctx.get("live_incidents") or [],
        drift_warnings=[str(drift.get("drift_alert", ""))] if drift.get("drift_alert") not in (None, "stable") else [],
        publish_failures=int((ctx.get("publish_stats") or {}).get("held_24h") or 0),
        runtime_unstable=float(pulse.get("event_loop_lag_max") or 0) >= 0.2
        or bool(pulse.get("stalled_loops")),
    )

    critical = [g for g in incidents if g.get("severity") == AttentionSeverity.CRITICAL.value]
    important = [g for g in incidents if g.get("severity") == AttentionSeverity.IMPORTANT.value]

    if critical or important:
        lines.append("<b>Incidents needing attention</b>")
        for g in critical + important[:4]:
            lines.append(
                f"🚨 {html.escape(g['title'])} ×{g.get('count', 1)} — "
                f"{html.escape(str(g.get('detail', ''))[:90])}",
            )
        lines.append("")

    ranked = ctx.get("priority_queue") or []
    risky = []
    for row in ranked[:10]:
        p = row.priority
        mem_warn = ()
        sev = AttentionSeverity.INFORMATIONAL
        for w in p.warnings:
            sev = max(sev, classify_editorial_warning(w), key=lambda s: s.rank)
        if p.editorial_priority_score >= 0.7 or sev.rank >= AttentionSeverity.IMPORTANT.rank:
            risky.append(row)
        elif p.warnings and sev.rank >= AttentionSeverity.IMPORTANT.rank:
            risky.append(row)

    if risky:
        lines.append("<b>Editorial decisions</b>")
        for row in risky[:6]:
            p = row.priority
            lines.append(
                "• "
                + html.escape(
                    compress_priority_rationale(
                        headline=row.headline,
                        urgency=p.urgency_class,
                        why=p.why_ranked,
                        storyline_id=row.storyline_id,
                        follow_up=row.memory_follow_up,
                    )[:160],
                ),
            )
            for w in p.warnings[:1]:
                lines.append(f"  ⚠ {html.escape(w[:70])}")
        lines.append("")

    fatigued = [
        s
        for s in (ctx.get("active_storylines") or [])
        if float(s.get("saturation") or 0) >= 0.6
    ]
    if fatigued:
        lines.append("<b>Fatigue hotspots</b>")
        for s in fatigued[:4]:
            lines.append(
                f"• <code>{html.escape(s['storyline_id'])}</code> "
                f"saturation {float(s['saturation']):.2f} — {html.escape(s['title'][:60])}",
            )

    if len(lines) <= 3:
        lines.append("No critical attention items — system stable.")
    return "\n".join(lines)
