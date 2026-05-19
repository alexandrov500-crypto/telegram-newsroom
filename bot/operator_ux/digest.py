from __future__ import annotations

import html
from datetime import datetime, timezone
from typing import Any

from bot.operator_ux.dedupe import bundle_runtime_signals
from bot.operator_ux.compress import compress_editorial_item


def _compression_enabled() -> bool:
    import os

    return os.getenv("DIGEST_SIGNAL_COMPRESSION", "true").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _has_critical_warnings(ctx: dict[str, Any]) -> bool:
    cockpit = (ctx.get("flow_governance") or {}).get("cockpit") or {}
    for w in cockpit.get("active_warnings") or []:
        if str(w.get("tier")) == "CRITICAL":
            return True
    return False


def build_operator_digest_html(ctx: dict[str, Any]) -> str:
    now = datetime.now(timezone.utc)
    pulse = ctx.get("pulse") or {}
    drift = ctx.get("priority_drift") or {}
    stats = ctx.get("publish_stats") or {}
    noise = ctx.get("noise_metrics") or {}
    compress = _compression_enabled()

    lines = [
        f"<b>Operator digest</b> · {now.strftime('%Y-%m-%d %H:%M')} UTC",
    ]

    if compress:
        try:
            from bot.editorial.flow_health.signal_compression import format_compressed_digest_html

            lines.extend(format_compressed_digest_html(ctx))
        except Exception:
            pass

    lines.extend(["", "<b>Runtime health</b>"])
    lines.extend([
        f"Mode: <code>{html.escape(str((ctx.get('live_state') or {}).get('live_mode', '?')))}</code> · "
        f"success {float(ctx.get('publish_success_rate') or 0):.0%}",
        f"Lag max: {float(pulse.get('event_loop_lag_max') or 0):.3f}s · "
        f"stalled loops: {len(pulse.get('stalled_loops') or [])}",
    ])
    runtime_bundle = bundle_runtime_signals(pulse)
    if runtime_bundle:
        lines.append(f"⚠ {html.escape(runtime_bundle[0])}")

    lines.extend(["", "<b>Editorial</b>"])
    lines.append(
        f"Drift: <code>{html.escape(str(drift.get('drift_alert', 'stable')))}</code> · "
        f"avg priority {drift.get('avg_priority', '—')}",
    )
    ranked = ctx.get("priority_queue") or []
    if ranked:
        lines.append("Top priority:")
        for row in ranked[:5]:
            p = row.priority
            lines.append(
                "• "
                + html.escape(
                    compress_editorial_item(
                        pending_id=row.item.id,
                        score=p.editorial_priority_score,
                        urgency=p.urgency_class,
                        headline=row.headline,
                        why=p.why_ranked,
                        warnings=p.warnings,
                    ),
                ),
            )
    else:
        lines.append("No pending queue items.")

    storylines = ctx.get("active_storylines") or []
    if storylines:
        lines.append("")
        lines.append("<b>Active storylines</b>")
        for s in storylines[:5]:
            lines.append(
                f"• <code>{html.escape(s['storyline_id'])}</code> "
                f"({s['publish_count']} posts, sat {float(s.get('saturation', 0)):.2f})",
            )

    lines.extend(["", "<b>Sources & quality</b>"])
    lines.append(
        f"Published 24h: {stats.get('published_24h', 0)} · held: {stats.get('held_24h', 0)} · "
        f"ratings: {stats.get('ratings', {})}",
    )

    inc = ctx.get("live_incidents") or []
    if inc:
        lines.append(f"Incidents (recent): {len(inc)}")

    lines.extend(["", "<b>Attention efficiency</b>"])
    lines.append(
        f"Delivered: {noise.get('delivered', 0)} · suppressed: {noise.get('suppressed', 0)} · "
        f"bundled: {noise.get('bundled', 0)}",
    )

    flow = ctx.get("publish_funnel") or {}
    if flow and (not compress or _has_critical_warnings(ctx) or (flow.get("starvation") or {}).get("detected")):
        lines.extend(["", "<b>Publish funnel (6h)</b>"])
        starve = flow.get("starvation") or {}
        if starve.get("detected"):
            lines.append(
                f"⚠ Starvation: {html.escape(str(starve.get('reason', '?')))} "
                f"({starve.get('published', 0)}/{starve.get('min_publish', 0)} publishes)",
            )
        counters = flow.get("counters") or {}
        lines.append(
            f"Fetched {counters.get('FETCHED', 0)} → published {counters.get('PUBLISHED', 0)} · "
            f"ratio {flow.get('publish_ratio', '—')}",
        )
        if flow.get("dominant_rejection"):
            lines.append(
                f"Top rejection: <code>{html.escape(str(flow['dominant_rejection']))}</code>",
            )
        adapt = ctx.get("flow_adaptive") or {}
        relax = adapt.get("relaxation") or {}
        if relax:
            lines.append(
                f"Relax budget {relax.get('relaxation_budget_used', '—')}/"
                f"{relax.get('relaxation_budget_max', '—')} · "
                f"hysteresis ×{relax.get('hysteresis_multiplier', '—')}",
            )
        if adapt.get("starvation_active"):
            lines.append(
                f"Floor active · cluster τ {adapt.get('cluster_similarity_threshold', '—')}",
            )
        attr = (starve.get("attribution") or {}).get("summary")
        if attr:
            lines.append(f"Causes: {html.escape(attr)}")
        cov = ctx.get("flow_coverage") or {}
        if cov:
            lines.append(
                f"Coverage {cov.get('coverage_score', '—')} "
                f"({cov.get('distinct_story_clusters', 0)} stories)",
            )
        trends = ctx.get("flow_trends") or {}
        if trends.get("permissive_drift_warning"):
            lines.append(f"⚠ {html.escape(str(trends.get('drift_interpretation', '')))}")
        elif trends.get("drift_interpretation"):
            lines.append(html.escape(str(trends["drift_interpretation"])[:120]))

    cadence = ctx.get("flow_cadence") or {}
    if cadence and not compress:
        lines.extend(["", "<b>Cadence (pilot)</b>"])
        exp = cadence.get("expected_window") or {}
        lines.append(
            f"Window {html.escape(str(exp.get('window', '?')))}: "
            f"{cadence.get('actual_window', 0)} published "
            f"(target {exp.get('min', '?')}–{exp.get('max', '?')})",
        )
        lines.append(
            f"Health {cadence.get('cadence_health', '—')} · "
            f"6h/24h: {cadence.get('actual_6h', 0)}/{cadence.get('actual_24h', 0)} · "
            f"band <code>{html.escape(str(cadence.get('cadence_band', '?')))}</code>",
        )
        canary = ctx.get("flow_canary") or {}
        if canary:
            lines.append(
                f"Canary cap {canary.get('effective_cap', '—')}"
                f" (base {canary.get('base_cap', '—')})",
            )
        dup24 = int(ctx.get("duplicate_escapes_24h") or 0)
        dup72 = int(ctx.get("duplicate_escapes_72h") or 0)
        if dup24 or dup72:
            lines.append(f"Duplicate escapes: {dup24} (24h) · {dup72} (72h)")
        starve = (flow.get("starvation") or {}) if flow else {}
        if starve.get("detected"):
            lines.append("Recovery floor: active")
        rej = flow.get("rejection_breakdown") if flow else None
        if rej:
            top = ", ".join(f"{k}:{v}" for k, v in list(rej.items())[:4])
            lines.append(f"Suppressions: {html.escape(top)}")

    cal = ctx.get("flow_calibration") or {}
    if cal and not compress:
        lines.extend(["", "<b>Newsroom rhythm</b>"])
        mode = (cal.get("newsroom_mode") or {}).get("current_mode", "?")
        lines.append(f"Mode: <code>{html.escape(str(mode))}</code>")
        pred = cal.get("predictability") or {}
        lines.append(
            f"Predictability {pred.get('predictability_score', '—')} "
            f"({html.escape(str(pred.get('predictability_band', '?')))})",
        )
        rhythm = cal.get("rhythm") or {}
        lines.append(
            f"Rhythm {html.escape(str(rhythm.get('rhythm_band', '?')))} · "
            f"stability {rhythm.get('rhythm_stability', '—')} · "
            f"2h/6h pubs {rhythm.get('publishes_2h', 0)}/{rhythm.get('publishes_6h', 0)}",
        )
        cat = cal.get("category_balance") or {}
        if cat.get("bucket_counts"):
            lines.append(
                f"Categories: dominant <code>{html.escape(str(cat.get('dominant_bucket', '?')))}</code> "
                f"({float(cat.get('dominant_ratio') or 0):.0%})",
            )
        dig = cal.get("digest_discipline") or {}
        if int(dig.get("digest_publishes") or 0) > 0:
            lines.append(
                f"Digest dependency {float(dig.get('digest_to_publish_ratio') or 0):.0%} "
                f"({dig.get('digest_publishes', 0)} recovery digests / 24h)",
            )
        thr = cal.get("threshold_stability") or {}
        if thr.get("threshold_stability_warning"):
            reasons = ", ".join(thr.get("warning_reasons") or [])[:80]
            lines.append(f"⚠ Threshold stability: {html.escape(reasons)}")
        wins = cal.get("windows") or {}
        w72 = (wins.get("72h") or {})
        if isinstance(w72, dict) and w72.get("publish_ratio_trend"):
            lines.append(
                f"72h trend: {html.escape(str(w72.get('publish_ratio_trend', '?')))} · "
                f"starvation hours {w72.get('starvation_hours', 0)}",
            )

    return "\n".join(lines)


def build_operator_digest_dict(ctx: dict[str, Any]) -> dict[str, Any]:
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "pulse_summary": {
            "lag_max": (ctx.get("pulse") or {}).get("event_loop_lag_max"),
            "stalled_loops": (ctx.get("pulse") or {}).get("stalled_loops"),
        },
        "priority_drift": ctx.get("priority_drift"),
        "top_priority_ids": [r.item.id for r in (ctx.get("priority_queue") or [])[:8]],
        "storylines": ctx.get("active_storylines"),
        "noise_metrics": ctx.get("noise_metrics"),
        "publish_stats": ctx.get("publish_stats"),
    }
