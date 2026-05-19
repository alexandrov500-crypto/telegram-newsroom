from __future__ import annotations

import html
from typing import Any

from bot.operator_ux.dedupe import bundle_runtime_signals
from bot.operator_ux.severity import AttentionSeverity


def _trend_arrow(current: float, threshold: float, *, higher_is_bad: bool = True) -> str:
    if current >= threshold:
        return "↑" if higher_is_bad else "↓"
    if current >= threshold * 0.7:
        return "→"
    return "↓" if higher_is_bad else "↑"


def build_live_dashboard_html(
    *,
    coordinator_snap: dict[str, Any],
    signals: dict[str, Any] | None,
    ctx: dict[str, Any] | None = None,
) -> str:
    """Actionable dashboard; avoids raw telemetry dumps."""
    sig = signals or {}
    pulse = (ctx or {}).get("pulse") or {}
    drift = (ctx or {}).get("priority_drift") or {}
    noise = (ctx or {}).get("noise_metrics") or {}
    perf = coordinator_snap.get("runtime_performance") or {}
    lh = perf.get("loop_health") or {}
    m = coordinator_snap.get("latest_metrics") or {}

    lag_max = float(perf.get("event_loop_lag_max") or pulse.get("event_loop_lag_max") or 0)
    lag_avg = float(perf.get("event_loop_lag_avg") or 0)
    stalled = int(lh.get("stalled_loop_count") or len(pulse.get("stalled_loops") or []))
    recovery = int(lh.get("recovery_attempt_count") or pulse.get("recovery_attempt_count") or 0)
    success = float(coordinator_snap.get("success_rate") or 0)

    stability = "🟢 Stable"
    if coordinator_snap.get("frozen") or lag_max >= 0.25 or stalled > 0:
        stability = "🔴 Attention needed"
    elif lag_max >= 0.12 or recovery > 2:
        stability = "🟡 Watch"

    lines = [
        "<b>Live ops dashboard</b>",
        f"<b>{stability}</b> · mode <code>{html.escape(str(coordinator_snap.get('live_mode', '?')))}</code>",
        "",
        "<b>Attention needed</b>",
    ]

    attention_items: list[str] = []
    if coordinator_snap.get("frozen"):
        attention_items.append("🚨 Publishing frozen")
    if stalled:
        attention_items.append(f"⚠ {stalled} stalled loops")
    if lag_max >= 0.15:
        attention_items.append(f"⚠ Loop lag {_trend_arrow(lag_max, 0.15)} {lag_max:.3f}s max")
    drift_alert = str(drift.get("drift_alert") or "stable")
    if drift_alert not in ("stable", ""):
        attention_items.append(f"⚠ Editorial drift: {drift_alert}")
    if int(coordinator_snap.get("quarantined_sources") or 0) > 0:
        attention_items.append(
            f"⚠ {coordinator_snap['quarantined_sources']} quarantined sources",
        )
    if not attention_items:
        attention_items.append("ℹ️ No critical items — routine monitoring")
    lines.extend(attention_items)

    runtime_bundle = bundle_runtime_signals(pulse)
    if runtime_bundle:
        lines.append(f"⚠ {html.escape(runtime_bundle[0])}")

    lines.extend(
        [
            "",
            "<b>Operational summary</b>",
            f"Publish success {success:.0%} {_trend_arrow(1 - success, 0.15, higher_is_bad=False)} · "
            f"rollbacks 24h: {coordinator_snap.get('rollback_24h', 0)}",
            f"Published/h: {m.get('published_last_hour', '?')} · held/h: {m.get('held_last_hour', '?')}",
            f"Trust {coordinator_snap['scores']['trust_score']:.0%} · "
            f"stability {coordinator_snap['scores']['content_stability_score']:.0%}",
            f"Survivability {float(sig.get('survivability_score', 0)):.0%}",
            "",
            "<b>Runtime (compressed)</b>",
            f"Lag avg/max: {lag_avg:.3f}s / {lag_max:.3f}s · "
            f"recovery {recovery} (suppressed {lh.get('recovery_suppressed_count', 0)})",
            f"Slow jobs: {perf.get('slow_job_count', 0)} · slow DB: {perf.get('slow_db_operation_count', 0)}",
            "",
            "<b>Noise control</b>",
            f"Suppressed 24h: {noise.get('suppressed', 0)} · "
            f"delivered: {noise.get('delivered', 0)} · "
            f"bundled: {noise.get('bundled', 0)}",
        ],
    )

    ranked = (ctx or {}).get("priority_queue") or []
    if ranked:
        top = ranked[0]
        lines.append(
            f"\n<b>Top editorial pick</b> #{top.item.id} "
            f"[{top.priority.editorial_priority_score:.2f}] "
            f"{html.escape(top.headline[:70])}",
        )
    return "\n".join(lines)
