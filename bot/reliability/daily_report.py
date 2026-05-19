from __future__ import annotations

from datetime import datetime, timezone

from bot.reliability.metrics_aggregator import AggregatedMetrics
from bot.reliability.types import RuntimeHealthSnapshot


def format_daily_operational_report(
    *,
    metrics: AggregatedMetrics,
    health: RuntimeHealthSnapshot | None,
    incident_summaries: list[str],
    subsystem_uptime: dict[str, float],
) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%MZ")
    lines = [
        f"<b>📊 Daily ops report</b> · {now}",
        "",
        f"Stories: <b>{metrics.stories_processed}</b> · candidates {metrics.publish_candidates}",
        f"Publish success: <b>{metrics.publish_success_rate * 100:.1f}%</b>",
        f"Token spend: <b>${metrics.token_usd:.2f}</b>",
        f"Cognition latency: <b>{metrics.cognition_latency_ms:.0f}ms</b>",
        f"Retries (1h): {metrics.retry_count} · failures logged {metrics.failure_count}",
    ]
    if metrics.top_sources:
        src = " · ".join(f"{n}({c})" for n, c in metrics.top_sources[:4])
        lines.append(f"Top sources: {src}")
    if health is not None:
        lines.extend([
            "",
            f"Health: <b>{health.overall_state.value}</b> score {health.health_score:.2f}",
            f"Mode: {health.publish_mode.value} · queue {health.queue_depth}",
        ])
        degraded = [s.name.value for s in health.subsystems if s.state.value != "HEALTHY"]
        if degraded:
            lines.append(f"Degraded: {', '.join(degraded)}")
    if subsystem_uptime:
        upt = " · ".join(f"{k}:{v:.0f}%" for k, v in list(subsystem_uptime.items())[:5])
        lines.append(f"Uptime: {upt}")
    if incident_summaries:
        lines.append("")
        lines.append("<b>Incidents (24h)</b>")
        for s in incident_summaries[:6]:
            lines.append(f"• {s[:90]}")
    lines.append("")
    lines.append("/health_live · /incidents_live · /recovery_live")
    return "\n".join(lines)
