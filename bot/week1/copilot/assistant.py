from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from bot.week1.repository import Week1Repository


@dataclass
class Week1OpsCopilot:
    """Grounded operational copilot — telemetry + memory only."""

    repository: Week1Repository

    def summarize(self, signals: dict[str, Any]) -> str:
        citations: list[str] = []
        lines = ["<b>Ops copilot</b> (week-1 stabilization)"]

        risk = float(signals.get("stabilization_risk", signals.get("launch_risk", 0.3)))
        lines.append(f"Stabilization risk: {risk:.2f}")
        citations.append("sig:stabilization_risk")

        if risk > 0.6:
            lines.append("→ Priority: review /stabilization_risk and consider shadow mode")
        elif float(signals.get("queue_depth", 0)) > 150:
            lines.append("→ Priority: drain queue before ramping publish rate")
            citations.append("sig:queue_depth")
        else:
            lines.append("→ System within normal week-1 envelope")

        lines.append(f"Rollout: <code>{signals.get('rollout_stage', '?')}</code>")
        lines.append(
            f"Publish health: {signals.get('publish_health', signals.get('quality_avg', 0)):.2f}",
        )
        if signals.get("war_room_active"):
            lines.append("⚠ Active war room — defer nonessential changes")
            citations.append("sig:war_room")

        overload = float(signals.get("operator_attention", 0.5))
        if overload > 0.75:
            lines.append("→ Operator load high — use /shift_handoff")
            citations.append("sig:operator_attention")

        baselines = self.repository.all_baselines()
        if baselines:
            lines.append(f"Baselines captured: {', '.join(baselines.keys())}")
            citations.append("db:week1_baselines")

        lines.append(f"\n<i>Sources: {', '.join(citations[:6])}</i>")
        lines.append("<i>No external recommendations — internal signals only.</i>")
        return "\n".join(lines)

    def what_changed_24h(self, signals: dict[str, Any]) -> str:
        baselines = self.repository.all_baselines()
        lines = ["<b>Changes (24h vs baseline)</b>"]
        if not baselines:
            lines.append("No baseline yet — will capture on stable tick.")
            return "\n".join(lines)

        q_base = (baselines.get("quality") or {}).get("quality_avg", 0.8)
        q_now = float(signals.get("quality_avg", 0.8))
        dq = q_now - q_base
        lines.append(f"Quality: {dq:+.2f} ({q_base:.2f} → {q_now:.2f})")

        qb = (baselines.get("queue") or {}).get("queue_depth", 0)
        qn = int(signals.get("queue_depth", 0))
        lines.append(f"Queue: {qn - qb:+d} ({qb} → {qn})")

        surv = self.repository.survivability_history(limit=2)
        if len(surv) >= 2:
            lines.append(
                f"Survivability: {surv[0]['survivability_score']:.2f} "
                f"(prev {surv[1]['survivability_score']:.2f})",
            )
        return "\n".join(lines)
