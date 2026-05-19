from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from bot.ops_evolution.repository import OpsEvolutionRepository


@dataclass
class MaintenanceOrchestrator:
    repository: OpsEvolutionRepository
    preferred_hour_utc: int = 4

    def propose_plan(self, *, signals: dict[str, Any]) -> dict[str, Any]:
        tasks: list[dict[str, str]] = [
            {"task": "worker_rejuvenation", "risk": "low"},
            {"task": "slo_snapshot_prune", "risk": "low"},
            {"task": "memory_archive", "risk": "low"},
        ]
        if signals.get("queue_depth", 0) > 200:
            tasks.append({"task": "queue_compaction", "risk": "medium"})
        if signals.get("fatigue_index", 0) > 0.5:
            tasks.append({"task": "rolling_restart_advisory", "risk": "medium"})

        risk = max(0.1, sum(0.2 if t["risk"] == "medium" else 0.05 for t in tasks))
        window = f"{self.preferred_hour_utc:02d}:00 UTC"
        plan_id = self.repository.save_maintenance_plan(
            window_utc=window,
            tasks=tasks,
            risk_score=risk,
        )
        return {"plan_id": plan_id, "window": window, "tasks": tasks, "risk": risk}

    def plan_text(self) -> str:
        plan = self.repository.latest_maintenance_plan()
        if not plan:
            return "No maintenance plan — run ops tick to generate."
        lines = [
            f"<b>Maintenance plan</b> <code>{plan['plan_id'][:8]}</code>",
            f"Window: {plan['window_utc']} · risk {plan['risk_score']:.0%}",
            f"Status: {plan['status']}",
        ]
        for t in plan.get("tasks", []):
            lines.append(f"• {t['task']} ({t['risk']})")
        lines.append("<i>Operator approval required before execution.</i>")
        return "\n".join(lines)

    def risk_text(self, *, signals: dict[str, Any]) -> str:
        plan = self.propose_plan(signals=signals)
        return (
            f"<b>Maintenance risk</b>\n"
            f"Proposed risk: {plan['risk']:.0%}\n"
            f"Tasks: {len(plan['tasks'])} · window {plan['window']}"
        )
