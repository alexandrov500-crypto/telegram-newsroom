from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from bot.ops_playbook.repository import OpsPlaybookRepository

logger = logging.getLogger(__name__)

_DRILL_SCENARIOS = (
    "publish_failure",
    "floodwait",
    "openai_degradation",
    "worker_crash",
    "quality_collapse",
    "rollback_rehearsal",
    "certification_rehearsal",
)


@dataclass
class OperatorTrainingSimulator:
    """Simulation only — never mutates production rollout or publish state."""

    repository: OpsPlaybookRepository
    _training_active: bool = field(default=False, init=False)

    @property
    def training_active(self) -> bool:
        return self._training_active

    def enable_training_mode(self) -> str:
        self._training_active = True
        logger.info("event=training_mode_enabled simulated_only=true")
        return (
            "<b>Training mode ON</b>\n"
            "Simulated drills only — no live rollout changes.\n"
            "Use /run_drill &lt;scenario&gt;"
        )

    def disable_training_mode(self) -> str:
        self._training_active = False
        return "Training mode OFF."

    def run_drill(self, scenario: str, operator_id: str) -> tuple[float, str]:
        key = scenario.strip().lower().replace("-", "_")
        if key not in _DRILL_SCENARIOS:
            return 0.0, f"Unknown scenario. Options: {', '.join(_DRILL_SCENARIOS)}"

        scores = {
            "publish_failure": 0.85,
            "floodwait": 0.8,
            "openai_degradation": 0.75,
            "worker_crash": 0.9,
            "quality_collapse": 0.7,
            "rollback_rehearsal": 0.95,
            "certification_rehearsal": 0.88,
        }
        score = scores.get(key, 0.5)
        detail = {
            "simulated": True,
            "steps": [
                "Acknowledge incident",
                "Run /rollout_rollback (simulated)",
                "Verify /queues_live",
                "Document in war room (simulated)",
            ],
            "live_state_mutated": False,
        }
        self.repository.save_drill(
            scenario=key,
            operator_id=operator_id,
            score=score,
            detail=detail,
        )
        text = (
            f"<b>Drill complete</b> · {key}\n"
            f"Score: {score:.0%} (simulated)\n"
            "No production state changed."
        )
        return score, text

    def results_html(self) -> str:
        rows = self.repository.recent_drills(limit=5)
        lines = ["<b>Drill results</b> (simulated)"]
        for r in rows:
            lines.append(
                f"• {r['scenario']}: {r['score']:.0%} by {r['operator_id']}",
            )
        if not rows:
            lines.append("No drills yet — /run_drill publish_failure")
        return "\n".join(lines)
