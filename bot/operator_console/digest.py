from __future__ import annotations

from typing import Any

from bot.operator_console.fatigue import FatigueSnapshot
from bot.operator_console.formatting import clamp_lines, format_header, now_utc_short
from bot.operator_console.scoring import OpsHealthScore

MAX_DIGEST_LINES = 12


def format_ops_digest(
    *,
    health: OpsHealthScore,
    fatigue: FatigueSnapshot,
    signals: dict[str, Any],
) -> str:
    lag = signals.get("replay_lag", "stable")
    lines = [
        format_header("OPS DIGEST", "ok"),
        f"Health <b>{health.overall:.2f}</b> ({health.trend})",
        f"Replay <b>{lag}</b> · mesh <b>{signals.get('mesh_health', 0):.2f}</b>",
        f"Ingestion <b>{health.ingestion:.2f}</b> · replay <b>{health.replay:.2f}</b>",
        f"Contradictions <b>{signals.get('open_contradictions', 0)}</b>",
        f"Misinfo pending <b>{signals.get('misinfo_alerts', 0)}</b>",
        f"Storage <b>+{signals.get('storage_growth_mb', 0):.0f}MB</b>",
        f"Operator load <b>{fatigue.load_label}</b> (fatigue {fatigue.score:.2f})",
    ]
    if fatigue.digest_mode:
        lines.append("Digest mode ON — non-critical grouped")
    if fatigue.overload_warning:
        lines.append("⚠ overload — check /ops_usability")
    lines.append(now_utc_short())
    return clamp_lines("\n".join(lines), max_lines=MAX_DIGEST_LINES)


def format_cognition_digest(
    *,
    mesh_health: float,
    reasoning_spend: float,
    reasoning_quota: float,
    route_mix: dict[str, int] | None = None,
) -> str:
    pct = 0.0 if reasoning_quota <= 0 else min(100.0, 100.0 * reasoning_spend / reasoning_quota)
    lines = [
        format_header("COGNITION DIGEST", "info"),
        f"Mesh <b>{mesh_health:.2f}</b> · reasoning <b>{pct:.0f}%</b> quota",
    ]
    if route_mix:
        top = sorted(route_mix.items(), key=lambda x: -x[1])[:3]
        lines.append("Routes: " + ", ".join(f"{k}={v}" for k, v in top))
    lines.append(now_utc_short())
    return clamp_lines("\n".join(lines), max_lines=MAX_DIGEST_LINES)


def format_epistemic_digest(
    *,
    open_contradictions: int,
    misinfo_pending: int,
    epistemic_stability: float,
    delta_contradictions: int = 0,
) -> str:
    delta_s = f"+{delta_contradictions}" if delta_contradictions else "0"
    lines = [
        format_header("EPISTEMIC DIGEST", "warn" if open_contradictions > 15 else "info"),
        f"Stability <b>{epistemic_stability:.2f}</b>",
        f"Open contradictions <b>{open_contradictions}</b> ({delta_s})",
        f"Misinfo pending <b>{misinfo_pending}</b>",
        "/contradictions_queue · /contradiction_details",
        now_utc_short(),
    ]
    return clamp_lines("\n".join(lines), max_lines=MAX_DIGEST_LINES)
