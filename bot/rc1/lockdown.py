from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from bot.rc1.settings import RC1_BUILD_ID
from bot.runtime.state import runtime_state

logger = logging.getLogger(__name__)


@dataclass
class Rc1LockdownController:
    """RC1 operational freeze — restrict unsafe runtime changes."""

    build_id: str = RC1_BUILD_ID
    active: bool = False
    _frozen_toggles: frozenset[str] = frozenset(
        {
            "experimental_cognition",
            "schema_migration",
            "rollout_escalation",
            "chaos_drills",
        },
    )

    def enable(self) -> None:
        self.active = True
        runtime_state.operational_mode = "rc1_lockdown"
        logger.info("event=rc1_lockdown_enabled build=%s", self.build_id)

    def disable(self) -> None:
        self.active = False
        if runtime_state.operational_mode == "rc1_lockdown":
            runtime_state.operational_mode = "normal"
        logger.info("event=rc1_lockdown_disabled")

    def is_toggle_frozen(self, toggle: str) -> bool:
        return self.active and toggle in self._frozen_toggles

    def require_signed_override(self, *, has_signature: bool, command: str) -> bool:
        if not self.active:
            return True
        if has_signature:
            return True
        logger.warning("event=rc1_override_denied command=%s", command)
        return False

    def allow_rollout_escalation(self, *, certified: bool) -> tuple[bool, str]:
        if not self.active:
            return True, "lockdown_off"
        if not certified:
            return False, "certification_required"
        return True, "ok"

    def block_experimental_cognition(self) -> bool:
        return self.is_toggle_frozen("experimental_cognition")

    def snapshot(self) -> dict[str, Any]:
        return {
            "build_id": self.build_id,
            "active": self.active,
            "frozen_toggles": list(self._frozen_toggles),
            "operational_mode": runtime_state.operational_mode,
        }

    def status_text(self) -> str:
        mark = "🔒" if self.active else "🔓"
        lines = [
            f"<b>{mark} RC1 lockdown</b>",
            f"Build: <code>{self.build_id}</code>",
            f"Active: {'yes' if self.active else 'no'}",
        ]
        if self.active:
            lines.append("Frozen: rollout escalation (without cert), chaos, experimental cognition")
        return "\n".join(lines)
