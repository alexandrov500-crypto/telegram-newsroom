from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from bot.live_deploy.repository import LiveDeployRepository
from bot.live_deploy.settings import LiveDeploySettings


@dataclass
class First72HMode:
    """Launch-window protections — auto-disable after stable hours."""

    settings: LiveDeploySettings
    repository: LiveDeployRepository

    def hours_since_start(self) -> float:
        st = self.repository.get_state()
        if not st:
            return 0.0
        try:
            start = datetime.fromisoformat(
                st["production_start_at"].replace("Z", "+00:00"),
            )
            return (datetime.now(timezone.utc) - start).total_seconds() / 3600.0
        except ValueError:
            return 0.0

    def active(self) -> bool:
        if not self.settings.first_72h_mode:
            return False
        st = self.repository.get_state()
        if st and not st.get("first_72h_active", 1):
            return False
        hours = self.hours_since_start()
        if hours >= self.settings.first_72h_hours:
            self.repository.set_first_72h(False)
            return False
        return True

    def thresholds(self) -> dict[str, Any]:
        if not self.active():
            return {
                "min_quality": self.settings.min_quality_public,
                "min_trust": self.settings.min_trust_public,
                "min_confidence": self.settings.min_confidence_public,
                "rollback_trigger": 0.12,
                "publish_pacing_multiplier": 1.0,
                "mandatory_approval": self.settings.mandatory_operator_approval,
                "trust_penalty_multiplier": 1.0,
                "anomaly_multiplier": 1.0,
            }
        return {
            "min_quality": max(self.settings.min_quality_public, 0.78),
            "min_trust": max(self.settings.min_trust_public, 0.82),
            "min_confidence": max(self.settings.min_confidence_public, 0.88),
            "rollback_trigger": 0.06,
            "publish_pacing_multiplier": 0.55,
            "mandatory_approval": True,
            "trust_penalty_multiplier": 1.2,
            "anomaly_multiplier": 1.4,
            "elevated_telemetry": True,
            "audit_retention": "extended",
        }

    def status_html(self) -> str:
        hrs = self.hours_since_start()
        active = self.active()
        t = self.thresholds()
        return (
            f"<b>First 72h mode</b> {'ON' if active else 'OFF'}\n"
            f"Elapsed: {hrs:.1f}h / {self.settings.first_72h_hours}h\n"
            f"Quality ≥{t['min_quality']:.2f} · trust ≥{t['min_trust']:.2f}\n"
            f"Approval required: {'yes' if t['mandatory_approval'] else 'no'}"
        )
