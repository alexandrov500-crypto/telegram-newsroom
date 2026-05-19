from __future__ import annotations

import html
from typing import Any


def build_resilience_status_html(snapshot: dict[str, Any]) -> str:
    posture = snapshot.get("posture", "unknown")
    reason = snapshot.get("posture_reason", "")
    deps = snapshot.get("dependencies") or {}
    budgets = snapshot.get("failure_budgets") or {}
    guidance = snapshot.get("guidance") or []
    forecast = snapshot.get("forecast") or {}
    ctx = snapshot.get("context") or snapshot.get("backpressure", {}).get("applied") or {}
    recovery = snapshot.get("recovery_quality") or {}

    lines = [
        f"<b>Operational resilience</b>",
        f"Posture: <code>{html.escape(str(posture))}</code>",
        html.escape(reason[:200]),
        "",
        "<b>Dependency health</b>",
    ]
    for name, info in deps.items():
        lines.append(
            f"• {html.escape(name)}: <code>{html.escape(str(info.get('band', '?')))}</code>",
        )

    lines.extend(["", "<b>Failure budgets</b>"])
    for key in ("runtime_instability", "alert_volume", "recovery_frequency"):
        box = budgets.get(key) or {}
        if isinstance(box, dict):
            exhausted = " ⚠" if box.get("exhausted") else ""
            lines.append(
                f"• {key}: {box.get('used')}/{box.get('budget')}{exhausted}",
            )

    lines.extend(["", "<b>Load shedding</b>"])
    lines.append(
        f"Publish ×{float(ctx.get('reduce_publish_attempts', 1)):.2f} · "
        f"analytics {'paused' if ctx.get('pause_background_analytics') else 'on'} · "
        f"archival {'suspended' if ctx.get('suspend_archival') else 'on'}",
    )

    lines.extend(["", "<b>Recovery quality (7d)</b>"])
    lines.append(
        f"Attempts {recovery.get('total', 0)} · ok {recovery.get('successful', 0)} · "
        f"storm {'yes' if recovery.get('recovery_storm') else 'no'}",
    )

    lines.extend(["", "<b>Pressure forecast</b>"])
    lines.append(
        f"<code>{html.escape(str(forecast.get('pressure_level', '?')))}</code> — "
        f"{html.escape(str(forecast.get('summary', '')))}",
    )

    if guidance:
        lines.extend(["", "<b>Operator guidance</b>"])
        for g in guidance[:5]:
            lines.append(f"• <b>{html.escape(str(g.get('title', '?')))}</b>")
            lines.append(f"  {html.escape(str(g.get('recommended_action', ''))[:180])}")

    return "\n".join(lines)
